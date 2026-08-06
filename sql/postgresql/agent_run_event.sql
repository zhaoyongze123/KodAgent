-- KodAgent Agent persistence schema.
-- Production must run this file through the deployment migration step before
-- starting Java or LangGraph. The CREATE IF NOT EXISTS clauses keep local
-- development upgrades repeatable.

CREATE TABLE IF NOT EXISTS agent_run (
    run_id VARCHAR(128) PRIMARY KEY,
    thread_id VARCHAR(128) NOT NULL,
    message_id VARCHAR(128),
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT,
    error_code VARCHAR(128),
    error_message VARCHAR(1000),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_event_cursor BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE agent_run ADD COLUMN IF NOT EXISTS last_event_cursor BIGINT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_agent_run_thread_scope_time
    ON agent_run (tenant_id, user_id, thread_id, started_at, run_id);
CREATE INDEX IF NOT EXISTS idx_agent_run_status_time
    ON agent_run (tenant_id, user_id, status, started_at);

CREATE SEQUENCE IF NOT EXISTS agent_run_event_cursor_seq;

CREATE TABLE IF NOT EXISTS agent_run_event (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(128) NOT NULL UNIQUE,
    run_id VARCHAR(128) NOT NULL,
    thread_id VARCHAR(128) NOT NULL,
    message_id VARCHAR(128),
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    sequence_no BIGINT NOT NULL DEFAULT nextval('agent_run_event_cursor_seq'),
    event_type VARCHAR(64) NOT NULL,
    event_data JSONB NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE agent_run_event ALTER COLUMN event_id TYPE VARCHAR(128);
ALTER TABLE agent_run_event ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

-- The database cursor is the only ordering source. Python-provided sequence values
-- are ignored by the Java write path. The repair below is deliberately one-time:
-- normal re-execution must never rewrite an already-issued durable cursor.
-- Keep repair, invariant enforcement, unique-index creation and the completion
-- marker in one transaction. A failed repair/index build therefore cannot leave
-- a false "migration completed" marker behind, even when a caller forgets to set
-- psql ON_ERROR_STOP.
BEGIN;

ALTER TABLE agent_run_event
    ALTER COLUMN sequence_no SET DEFAULT nextval('agent_run_event_cursor_seq');

CREATE TABLE IF NOT EXISTS agent_schema_migration (
    version VARCHAR(128) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$
DECLARE
    migration_version CONSTANT VARCHAR(128) := 'agent_run_event_durable_cursor_v1';
    row_record RECORD;
    max_cursor BIGINT;
    sequence_last BIGINT;
    sequence_called BOOLEAN;
    repaired_cursor BIGINT;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM agent_schema_migration WHERE version = migration_version) THEN
        SELECT COALESCE(MAX(sequence_no), 0) INTO max_cursor FROM agent_run_event;
        SELECT last_value, is_called INTO sequence_last, sequence_called
          FROM agent_run_event_cursor_seq;

        -- Never move the sequence backwards. If it is behind the existing data,
        -- advance it before repairing duplicates so newly allocated values cannot
        -- collide with an already durable cursor. For an empty/legacy sequence,
        -- is_called=false keeps the first generated cursor at 1 (not 2).
        IF NOT sequence_called THEN
            IF max_cursor = 0 THEN
                PERFORM setval('agent_run_event_cursor_seq', 1, false);
            ELSE
                PERFORM setval('agent_run_event_cursor_seq', max_cursor, true);
            END IF;
        ELSIF sequence_last <= max_cursor THEN
            PERFORM setval('agent_run_event_cursor_seq', GREATEST(max_cursor, 1), true);
        END IF;

        -- Preserve the first row for every valid cursor and repair only invalid
        -- or duplicate rows. Ordering by id makes the one-time repair deterministic.
        FOR row_record IN
            SELECT id
            FROM (
                SELECT id, sequence_no,
                       ROW_NUMBER() OVER (PARTITION BY sequence_no ORDER BY id) AS row_number
                FROM agent_run_event
            ) ranked
            WHERE sequence_no IS NULL OR sequence_no <= 0 OR row_number > 1
            ORDER BY id
        LOOP
            repaired_cursor := nextval('agent_run_event_cursor_seq');
            UPDATE agent_run_event
               SET sequence_no = repaired_cursor,
                   event_data = jsonb_set(
                       jsonb_set(
                           jsonb_set(COALESCE(event_data, '{}'::jsonb),
                                     '{sequence}', to_jsonb(repaired_cursor), true),
                           '{runSequence}', to_jsonb(repaired_cursor), true),
                       '{eventCursor}',
                       jsonb_build_object('cursor', repaired_cursor, 'eventId', event_id,
                                          'databaseId', id, 'eventTime', event_time), true)
             WHERE id = row_record.id;
        END LOOP;
    END IF;
END $$;

-- The repair above is complete before this constraint is created. Existing valid
-- cursors are never rewritten; only legacy NULL/invalid/duplicate rows receive a
-- new cursor. This also makes old nullable installations converge to the same
-- invariant as a fresh installation.
ALTER TABLE agent_run_event
    ALTER COLUMN sequence_no SET NOT NULL;

-- This must be created only after the one-time repair, otherwise old duplicate
-- rows would make the migration fail before they can be repaired.
DO $$
DECLARE
    index_schema TEXT;
    index_name TEXT;
    index_is_unique BOOLEAN;
BEGIN
    SELECT n.nspname, c.relname, i.indisunique
      INTO index_schema, index_name, index_is_unique
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_index i ON i.indexrelid = c.oid
     WHERE n.nspname = current_schema()
       AND c.relname = 'uk_agent_run_event_sequence_no';
    IF FOUND AND NOT index_is_unique THEN
        EXECUTE format('DROP INDEX %I.%I', index_schema, index_name);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_run_event_sequence_no
    ON agent_run_event (sequence_no);

INSERT INTO agent_schema_migration (version)
VALUES ('agent_run_event_durable_cursor_v1')
ON CONFLICT (version) DO NOTHING;

COMMIT;

CREATE INDEX IF NOT EXISTS idx_agent_run_event_thread_scope_time
    ON agent_run_event (tenant_id, user_id, thread_id, event_time, id);
CREATE INDEX IF NOT EXISTS idx_agent_run_event_run_scope_sequence
    ON agent_run_event (tenant_id, user_id, run_id, sequence_no, id);

CREATE TABLE IF NOT EXISTS agent_run_event_outbox (
    event_id VARCHAR(128) PRIMARY KEY,
    stream_key VARCHAR(256) NOT NULL,
    payload JSONB NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    last_error VARCHAR(1000),
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE agent_run_event_outbox ALTER COLUMN event_id TYPE VARCHAR(128);
ALTER TABLE agent_run_event_outbox ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_agent_event_outbox_pending
    ON agent_run_event_outbox (next_attempt_at, created_at)
    WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS agent_approval (
    approval_id VARCHAR(64) PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    approver_user_id BIGINT NOT NULL,
    run_id VARCHAR(128) NOT NULL,
    thread_id VARCHAR(128) NOT NULL,
    message_id VARCHAR(128),
    task_id VARCHAR(128),
    operation_id VARCHAR(128),
    draft_id VARCHAR(64),
    status VARCHAR(32) NOT NULL,
    idempotency_key VARCHAR(128),
    resume_idempotency_key VARCHAR(128),
    approved_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    rejected_reason VARCHAR(500),
    resumed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_agent_approval_idempotency
        UNIQUE (tenant_id, approver_user_id, idempotency_key)
);
ALTER TABLE agent_approval ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
ALTER TABLE agent_approval ADD COLUMN IF NOT EXISTS message_id VARCHAR(128);
ALTER TABLE agent_approval ADD COLUMN IF NOT EXISTS task_id VARCHAR(128);
ALTER TABLE agent_approval ADD COLUMN IF NOT EXISTS resume_idempotency_key VARCHAR(128);
ALTER TABLE agent_approval ADD COLUMN IF NOT EXISTS resumed_at TIMESTAMPTZ;
ALTER TABLE agent_approval ADD COLUMN IF NOT EXISTS draft_type VARCHAR(64);
ALTER TABLE agent_approval ADD COLUMN IF NOT EXISTS draft_data JSONB;
ALTER TABLE agent_approval ADD COLUMN IF NOT EXISTS operation_id VARCHAR(128);

CREATE INDEX IF NOT EXISTS idx_agent_approval_user_status
    ON agent_approval (tenant_id, approver_user_id, status, expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_approval_pending_draft
    ON agent_approval (tenant_id, approver_user_id, draft_id)
    WHERE draft_id IS NOT NULL AND status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_agent_approval_run_binding
    ON agent_approval (tenant_id, approver_user_id, run_id, thread_id, message_id, task_id);
CREATE INDEX IF NOT EXISTS idx_agent_approval_operation_binding
    ON agent_approval (tenant_id, approver_user_id, operation_id, status)
    WHERE operation_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_approval_resume_idempotency
    ON agent_approval (tenant_id, approver_user_id, resume_idempotency_key)
    WHERE resume_idempotency_key IS NOT NULL;

-- A batch action is always previewed first.  This stores only allowlisted
-- display facts and a short-lived confirmation proof; BPM form variables are
-- deliberately never copied into the Agent event store.
CREATE TABLE IF NOT EXISTS agent_approval_batch_preview (
    preview_id VARCHAR(64) PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    owner_user_id BIGINT NOT NULL,
    preview_message_id VARCHAR(128) NOT NULL,
    run_id VARCHAR(128),
    thread_id VARCHAR(128),
    operation_id VARCHAR(128),
    confirmation_token VARCHAR(128) NOT NULL,
    confirmation_message_id VARCHAR(128),
    decision_idempotency_key VARCHAR(128),
    approved_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    rejected_reason VARCHAR(500),
    idempotency_key VARCHAR(128),
    status VARCHAR(32) NOT NULL,
    preview_data JSONB NOT NULL,
    result_data JSONB,
    expires_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_approval_batch_preview_status
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTING', 'COMPLETED', 'FAILED', 'EXPIRED'))
);
CREATE INDEX IF NOT EXISTS idx_agent_approval_batch_preview_owner_status
    ON agent_approval_batch_preview (tenant_id, owner_user_id, status, expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_approval_batch_preview_idempotency
    ON agent_approval_batch_preview (tenant_id, owner_user_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
-- Safe for environments that created the table before batch ApprovalCard was
-- introduced. PostgreSQL applies these independently on an existing table.
ALTER TABLE agent_approval_batch_preview ADD COLUMN IF NOT EXISTS decision_idempotency_key VARCHAR(128);
ALTER TABLE agent_approval_batch_preview ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
ALTER TABLE agent_approval_batch_preview ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ;
ALTER TABLE agent_approval_batch_preview ADD COLUMN IF NOT EXISTS rejected_reason VARCHAR(500);
ALTER TABLE agent_approval_batch_preview ADD COLUMN IF NOT EXISTS operation_id VARCHAR(128);
ALTER TABLE agent_approval_batch_preview DROP CONSTRAINT IF EXISTS ck_agent_approval_batch_preview_status;
ALTER TABLE agent_approval_batch_preview ADD CONSTRAINT ck_agent_approval_batch_preview_status
    CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTING', 'COMPLETED', 'FAILED', 'EXPIRED'));
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_approval_batch_preview_decision_idempotency
    ON agent_approval_batch_preview (tenant_id, owner_user_id, decision_idempotency_key)
    WHERE decision_idempotency_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_approval_batch_preview_operation
    ON agent_approval_batch_preview (tenant_id, owner_user_id, operation_id)
    WHERE operation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_approval_batch_preview_operation
    ON agent_approval_batch_preview (tenant_id, owner_user_id, operation_id)
    WHERE operation_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS agent_meeting_booking_draft (
    draft_id VARCHAR(64) PRIMARY KEY,
    approval_id VARCHAR(64),
    tenant_id BIGINT NOT NULL,
    owner_user_id BIGINT NOT NULL,
    run_id VARCHAR(128) NOT NULL,
    thread_id VARCHAR(128) NOT NULL,
    message_id VARCHAR(128) NOT NULL,
    task_id VARCHAR(128),
    operation_id VARCHAR(128),
    idempotency_key VARCHAR(128),
    status VARCHAR(32) NOT NULL,
    draft_data JSONB NOT NULL,
    result_data JSONB,
    expires_at TIMESTAMPTZ NOT NULL,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Upgrade path for the first prototype schema.
ALTER TABLE agent_meeting_booking_draft
    ADD COLUMN IF NOT EXISTS approval_id VARCHAR(64);
ALTER TABLE agent_meeting_booking_draft
    ADD COLUMN IF NOT EXISTS run_id VARCHAR(128);
ALTER TABLE agent_meeting_booking_draft
    ADD COLUMN IF NOT EXISTS thread_id VARCHAR(128);
ALTER TABLE agent_meeting_booking_draft
    ADD COLUMN IF NOT EXISTS message_id VARCHAR(128);
ALTER TABLE agent_meeting_booking_draft
    ADD COLUMN IF NOT EXISTS task_id VARCHAR(128);
ALTER TABLE agent_meeting_booking_draft
    ADD COLUMN IF NOT EXISTS operation_id VARCHAR(128);
ALTER TABLE agent_meeting_booking_draft
    ADD COLUMN IF NOT EXISTS tenant_id BIGINT;
ALTER TABLE agent_meeting_booking_draft
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128);
ALTER TABLE agent_meeting_booking_draft
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
ALTER TABLE agent_meeting_booking_draft
    ADD COLUMN IF NOT EXISTS result_data JSONB;

-- Legacy prototype rows may not have a current-turn identity. Preserve them as
-- audit history, make them inactive, and assign row-specific sentinels so the
-- new NOT NULL invariant applies only to newly-created business facts.
UPDATE agent_meeting_booking_draft
   SET archived_at = COALESCE(archived_at, CURRENT_TIMESTAMP),
       run_id = COALESCE(run_id, 'legacy-run:' || draft_id),
       thread_id = COALESCE(thread_id, 'legacy-thread:' || draft_id),
       message_id = COALESCE(message_id, 'legacy-message:' || draft_id)
 WHERE run_id IS NULL OR thread_id IS NULL OR message_id IS NULL;

-- Existing local drafts belong to the local development tenant. In production,
-- replace this backfill with the tenant mapping agreed during the migration.
UPDATE agent_meeting_booking_draft SET tenant_id = 1 WHERE tenant_id IS NULL;
ALTER TABLE agent_meeting_booking_draft ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE agent_meeting_booking_draft ALTER COLUMN run_id SET NOT NULL;
ALTER TABLE agent_meeting_booking_draft ALTER COLUMN thread_id SET NOT NULL;
ALTER TABLE agent_meeting_booking_draft ALTER COLUMN message_id SET NOT NULL;

-- The old prototype index allowed a key to collide across different Agent
-- turns. Recreate it with the complete current-turn binding.
DROP INDEX IF EXISTS uk_agent_draft_idempotency;
CREATE UNIQUE INDEX uk_agent_draft_idempotency
    ON agent_meeting_booking_draft (tenant_id, owner_user_id, idempotency_key,
                                    run_id, thread_id, message_id)
    WHERE idempotency_key IS NOT NULL AND archived_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_agent_draft_owner_status
    ON agent_meeting_booking_draft (tenant_id, owner_user_id, status, expires_at);
CREATE INDEX IF NOT EXISTS idx_agent_draft_scope_status
    ON agent_meeting_booking_draft (tenant_id, owner_user_id, status, expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_draft_approval
    ON agent_meeting_booking_draft (approval_id)
    WHERE approval_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_draft_run_binding
    ON agent_meeting_booking_draft (tenant_id, owner_user_id, run_id, thread_id, message_id, task_id);
CREATE INDEX IF NOT EXISTS idx_agent_draft_operation_binding
    ON agent_meeting_booking_draft (tenant_id, owner_user_id, operation_id, status)
    WHERE operation_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_agent_approval_status') THEN
        ALTER TABLE agent_approval ADD CONSTRAINT ck_agent_approval_status
            CHECK (status IN ('PENDING', 'APPROVED', 'SUBMITTING', 'COMPLETED', 'REJECTED', 'EXPIRED'));
    ELSE
        ALTER TABLE agent_approval DROP CONSTRAINT ck_agent_approval_status;
        ALTER TABLE agent_approval ADD CONSTRAINT ck_agent_approval_status
            CHECK (status IN ('PENDING', 'APPROVED', 'SUBMITTING', 'COMPLETED', 'REJECTED', 'EXPIRED'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_agent_draft_status') THEN
        ALTER TABLE agent_meeting_booking_draft ADD CONSTRAINT ck_agent_draft_status
            CHECK (status IN ('PENDING', 'SUBMITTING', 'SUBMITTED', 'CANCELLED'));
    END IF;
END $$;

COMMENT ON TABLE agent_run IS 'KodAgent Agent 一次运行的生命周期、状态和执行耗时';
COMMENT ON TABLE agent_run_event IS 'KodAgent Agent 运行过程事件，保存计划正文、工具调用、子 Agent 摘要和审批事件';
COMMENT ON TABLE agent_run_event_outbox IS 'Agent 事件可靠投递 Outbox，Redis 不可用时用于重试和补偿';
COMMENT ON TABLE agent_schema_migration IS 'KodAgent PostgreSQL 迁移版本标记，防止重复迁移重写审计数据';
COMMENT ON TABLE agent_approval IS 'Human-in-the-loop 审批事实记录，绑定租户、用户、Run 和草稿';
COMMENT ON TABLE agent_meeting_booking_draft IS '会议室预约 Human-in-the-loop 草稿及业务状态；run/thread/message 是当前轮必填绑定，历史缺失行归档并使用 legacy 标记';

COMMENT ON COLUMN agent_run_event.event_id IS '事件唯一 ID（最长 128 字符），用于幂等去重';
COMMENT ON COLUMN agent_run_event.run_id IS '一次 Agent 运行 ID';
COMMENT ON COLUMN agent_run_event.thread_id IS 'LangGraph 对话 Thread ID';
COMMENT ON COLUMN agent_run_event.message_id IS '用户本轮消息 ID，用于隔离每轮过程';
COMMENT ON COLUMN agent_run_event.tenant_id IS '租户 ID';
COMMENT ON COLUMN agent_run_event.user_id IS '发起用户 ID';
COMMENT ON COLUMN agent_run_event.sequence_no IS 'PostgreSQL 分配的 durable event cursor；不信任客户端 sequence，按此字段重放';
COMMENT ON COLUMN agent_run_event.event_type IS '事件类型，例如 progress、tool.started、approval.required';
COMMENT ON COLUMN agent_run_event.event_data IS '完整事件信封 JSON';
COMMENT ON COLUMN agent_run_event.event_time IS '事件发生时间';
COMMENT ON COLUMN agent_run_event.created_at IS '事件写入数据库时间';
COMMENT ON COLUMN agent_run_event.archived_at IS '事件归档时间，归档不改变审计事实';

COMMENT ON COLUMN agent_run.run_id IS '一次 Agent 运行唯一 ID';
COMMENT ON COLUMN agent_run.thread_id IS 'LangGraph 对话 Thread ID';
COMMENT ON COLUMN agent_run.message_id IS '触发本轮运行的用户消息 ID';
COMMENT ON COLUMN agent_run.status IS 'RUNNING、PAUSED、COMPLETED、FAILED、CANCELLED';
COMMENT ON COLUMN agent_run.started_at IS '运行开始时间';
COMMENT ON COLUMN agent_run.completed_at IS '运行结束时间';
COMMENT ON COLUMN agent_run.duration_ms IS '运行总耗时，毫秒';
COMMENT ON COLUMN agent_run.error_code IS '运行失败错误码';
COMMENT ON COLUMN agent_run.error_message IS '运行失败摘要，禁止写入密钥';
COMMENT ON COLUMN agent_run.metadata IS '运行元数据，不保存敏感凭据';
COMMENT ON COLUMN agent_run.last_event_cursor IS '最近一次成功落库并应用到运行状态的 durable event cursor，保证状态单调推进';

COMMENT ON COLUMN agent_run_event_outbox.event_id IS '对应 agent_run_event.event_id（最长 128 字符）';
COMMENT ON COLUMN agent_run_event_outbox.attempts IS 'Redis 投递尝试次数';
COMMENT ON COLUMN agent_run_event_outbox.next_attempt_at IS '下一次允许重试的时间';
COMMENT ON COLUMN agent_run_event_outbox.published_at IS '成功写入 Redis Stream 的时间';
COMMENT ON COLUMN agent_run_event_outbox.last_error IS '最近一次投递失败原因，禁止写入密钥和身份票据';
COMMENT ON COLUMN agent_run_event_outbox.archived_at IS 'Outbox 归档时间';

COMMENT ON COLUMN agent_approval.tenant_id IS '审批所属租户';
COMMENT ON COLUMN agent_approval.approver_user_id IS '允许操作该审批的用户';
COMMENT ON COLUMN agent_approval.run_id IS '审批对应的 Agent Run ID';
COMMENT ON COLUMN agent_approval.thread_id IS '审批对应的 LangGraph Thread ID';
COMMENT ON COLUMN agent_approval.message_id IS '触发审批的用户消息 ID';
COMMENT ON COLUMN agent_approval.task_id IS '当前 Agent task/subagent 绑定 ID';
COMMENT ON COLUMN agent_approval.resume_idempotency_key IS 'LangGraph resume 请求幂等键';
COMMENT ON COLUMN agent_approval.resumed_at IS '恢复请求记录时间';
COMMENT ON COLUMN agent_approval.idempotency_key IS '确认或拒绝操作幂等键';
COMMENT ON COLUMN agent_approval.status IS 'PENDING、APPROVED、REJECTED、EXPIRED';
COMMENT ON COLUMN agent_approval.archived_at IS '审批归档时间';

COMMENT ON COLUMN agent_meeting_booking_draft.tenant_id IS '草稿所属租户';
COMMENT ON COLUMN agent_meeting_booking_draft.owner_user_id IS '草稿所属用户';
COMMENT ON COLUMN agent_meeting_booking_draft.run_id IS '草稿对应的 Agent Run ID；新业务必填，历史缺失行使用 legacy 标记并归档';
COMMENT ON COLUMN agent_meeting_booking_draft.thread_id IS '草稿对应的 LangGraph Thread ID；新业务必填，历史缺失行使用 legacy 标记并归档';
COMMENT ON COLUMN agent_meeting_booking_draft.message_id IS '创建草稿的用户消息 ID；新业务必填，用于隔离当前对话轮次';
COMMENT ON COLUMN agent_meeting_booking_draft.task_id IS '创建草稿的 Agent task/subagent ID';
COMMENT ON COLUMN agent_meeting_booking_draft.idempotency_key IS '同一租户、用户、Run、Thread、Message 请求的草稿幂等键';
COMMENT ON COLUMN agent_meeting_booking_draft.status IS 'PENDING、SUBMITTING、SUBMITTED、CANCELLED';
COMMENT ON COLUMN agent_meeting_booking_draft.draft_data IS '预约草稿 JSON 数据';
COMMENT ON COLUMN agent_meeting_booking_draft.result_data IS '预约提交后的业务结果 JSON，用于幂等重试回放';
COMMENT ON COLUMN agent_meeting_booking_draft.expires_at IS '草稿过期时间';
COMMENT ON COLUMN agent_meeting_booking_draft.archived_at IS '草稿归档时间，业务删除使用状态变更';

-- Personal schedules use their own draft boundary.  They must never be
-- represented as meeting-booking drafts: a meeting booking is an immutable
-- room allocation, while a personal schedule is owned and versioned by its
-- creator.
CREATE TABLE IF NOT EXISTS agent_personal_schedule_draft (
    draft_id VARCHAR(64) PRIMARY KEY,
    approval_id VARCHAR(64) NOT NULL UNIQUE,
    tenant_id BIGINT NOT NULL,
    owner_user_id BIGINT NOT NULL,
    run_id VARCHAR(128) NOT NULL,
    thread_id VARCHAR(128) NOT NULL,
    message_id VARCHAR(128) NOT NULL,
    task_id VARCHAR(128),
    operation_id VARCHAR(128),
    idempotency_key VARCHAR(128) NOT NULL,
    operation VARCHAR(16) NOT NULL,
    source_schedule_id BIGINT,
    source_version VARCHAR(64),
    status VARCHAR(32) NOT NULL,
    draft_data JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_personal_schedule_draft_operation
        CHECK (operation IN ('CREATE', 'UPDATE', 'CANCEL')),
    CONSTRAINT ck_agent_personal_schedule_draft_status
        CHECK (status IN ('PENDING', 'SUBMITTING', 'SUBMITTED', 'CANCELLED'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_personal_schedule_draft_idempotency
    ON agent_personal_schedule_draft (tenant_id, owner_user_id, idempotency_key,
                                      run_id, thread_id, message_id)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_agent_personal_schedule_draft_owner_status
    ON agent_personal_schedule_draft (tenant_id, owner_user_id, status, expires_at);
COMMENT ON TABLE agent_personal_schedule_draft IS '个人日程 Human-in-the-loop 草稿；不与会议室预约草稿混用';
-- Existing environments may already have the table from an earlier rollout.
-- Preserve their pending drafts while making successful commit retries
-- return the original result instead of attempting a second write.
ALTER TABLE agent_personal_schedule_draft
    ADD COLUMN IF NOT EXISTS result_data JSONB;
ALTER TABLE agent_personal_schedule_draft
    ADD COLUMN IF NOT EXISTS operation_id VARCHAR(128);
CREATE INDEX IF NOT EXISTS idx_agent_personal_schedule_draft_operation
    ON agent_personal_schedule_draft (tenant_id, owner_user_id, operation_id, status)
    WHERE operation_id IS NOT NULL;

-- Party files use their own durable HITL boundary. The agent never writes
-- party_file directly: a confirmed draft is revalidated by Java on commit.
CREATE TABLE IF NOT EXISTS agent_party_file_draft (
    draft_id VARCHAR(64) PRIMARY KEY,
    approval_id VARCHAR(64) NOT NULL UNIQUE,
    tenant_id BIGINT NOT NULL,
    owner_user_id BIGINT NOT NULL,
    run_id VARCHAR(128) NOT NULL,
    thread_id VARCHAR(128) NOT NULL,
    message_id VARCHAR(128) NOT NULL,
    task_id VARCHAR(128),
    operation_id VARCHAR(128),
    idempotency_key VARCHAR(128) NOT NULL,
    operation VARCHAR(16) NOT NULL,
    source_party_file_id BIGINT,
    source_snapshot JSONB,
    status VARCHAR(32) NOT NULL,
    draft_data JSONB NOT NULL,
    result_data JSONB,
    expires_at TIMESTAMPTZ NOT NULL,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_party_file_draft_operation CHECK (operation IN ('CREATE', 'UPDATE', 'DELETE')),
    CONSTRAINT ck_agent_party_file_draft_status CHECK (status IN ('PENDING', 'SUBMITTING', 'SUBMITTED', 'CANCELLED'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_party_file_draft_idempotency
    ON agent_party_file_draft (tenant_id, owner_user_id, idempotency_key, run_id, thread_id, message_id)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_agent_party_file_draft_owner_status
    ON agent_party_file_draft (tenant_id, owner_user_id, status, expires_at);
ALTER TABLE agent_party_file_draft ADD COLUMN IF NOT EXISTS operation_id VARCHAR(128);
CREATE INDEX IF NOT EXISTS idx_agent_party_file_draft_operation
    ON agent_party_file_draft (tenant_id, owner_user_id, operation_id, status)
    WHERE operation_id IS NOT NULL;
COMMENT ON TABLE agent_party_file_draft IS '党务文件 Human-in-the-loop 草稿；CREATE status=ENABLE 即正式发布';

-- Party-file drafts created by the former Redis-marker protocol cannot be
-- resumed safely because they have no Operation identity. Preserve them as
-- audit history, but make the old pending cards explicitly terminal so the
-- new Operation-bound flow never has to guess what they meant.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM agent_schema_migration
        WHERE version = 'agent_party_file_operation_binding_v1'
    ) THEN
        UPDATE agent_party_file_draft
           SET status = 'CANCELLED', archived_at = CURRENT_TIMESTAMP,
               updated_at = CURRENT_TIMESTAMP
         WHERE status = 'PENDING' AND operation_id IS NULL;
        UPDATE agent_approval
           SET status = 'REJECTED', rejected_at = CURRENT_TIMESTAMP,
               rejected_reason = '旧党务文件审批协议已失效，请重新生成草稿',
               updated_at = CURRENT_TIMESTAMP
         WHERE draft_type = 'PARTY_FILE' AND status = 'PENDING'
           AND operation_id IS NULL;
        INSERT INTO agent_schema_migration (version)
        VALUES ('agent_party_file_operation_binding_v1');
    END IF;
END $$;

-- These records are written by the only schema writer: the deployment
-- migration job. Java verifies them at startup but never performs DDL itself.
INSERT INTO agent_schema_migration (version) VALUES
    ('agent_approval_confirmation_contract_v1'),
    ('agent_approval_batch_confirmation_contract_v1'),
    ('agent_meeting_booking_commit_result_v1'),
    ('agent_personal_schedule_commit_result_v1'),
    ('agent_party_file_commit_result_v1')
ON CONFLICT (version) DO NOTHING;
