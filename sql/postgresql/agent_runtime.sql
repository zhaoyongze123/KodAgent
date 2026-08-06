-- KodAgent Python runtime facts.  This schema is separate from LangGraph
-- checkpoint tables and OA business tables.  Apply it through the single
-- runtime migration job, never from application startup code.

CREATE SCHEMA IF NOT EXISTS agent_runtime;

CREATE TABLE IF NOT EXISTS agent_runtime.schema_migration (
    version VARCHAR(128) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_runtime.operation (
    operation_id VARCHAR(128) PRIMARY KEY,
    action_id VARCHAR(128) NOT NULL,
    capability_id VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    thread_id VARCHAR(128) NOT NULL,
    origin_run_id VARCHAR(128) NOT NULL,
    current_run_id VARCHAR(128) NOT NULL,
    message_id VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    payload_schema_version INTEGER NOT NULL DEFAULT 1,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    plan_id VARCHAR(128),
    plan_revision INTEGER,
    approval_id VARCHAR(128),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_runtime_operation_status CHECK (
        status IN ('CREATED', 'COLLECTING_INFO', 'READY', 'RUNNING',
                   'WAITING_APPROVAL', 'COMMITTING', 'SUCCEEDED', 'FAILED',
                   'CANCELLED', 'EXPIRED', 'UNKNOWN')
    ),
    CONSTRAINT ck_agent_runtime_operation_version CHECK (version >= 1),
    CONSTRAINT ck_agent_runtime_operation_plan_revision CHECK (plan_revision IS NULL OR plan_revision >= 1)
);

CREATE INDEX IF NOT EXISTS idx_agent_runtime_operation_scope
    ON agent_runtime.operation (tenant_id, user_id, thread_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runtime_operation_status
    ON agent_runtime.operation (tenant_id, user_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_runtime.operation_transition (
    transition_id BIGSERIAL PRIMARY KEY,
    operation_id VARCHAR(128) NOT NULL REFERENCES agent_runtime.operation(operation_id),
    from_status VARCHAR(32) NOT NULL,
    to_status VARCHAR(32) NOT NULL,
    from_version BIGINT NOT NULL,
    to_version BIGINT NOT NULL,
    run_id VARCHAR(128),
    causation_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_runtime_operation_transition_operation
    ON agent_runtime.operation_transition (operation_id, to_version);

CREATE TABLE IF NOT EXISTS agent_runtime.effect (
    effect_id VARCHAR(128) PRIMARY KEY,
    operation_id VARCHAR(128) NOT NULL REFERENCES agent_runtime.operation(operation_id),
    action_id VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(256) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    lease_owner VARCHAR(128),
    lease_until TIMESTAMPTZ,
    reconcile_strategy VARCHAR(128) NOT NULL,
    request_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_agent_runtime_effect_idempotency UNIQUE (operation_id, idempotency_key),
    CONSTRAINT ck_agent_runtime_effect_status CHECK (
        status IN ('PLANNED', 'CLAIMED', 'EXECUTING', 'SUCCEEDED',
                   'FAILED_RETRYABLE', 'FAILED_FINAL', 'UNKNOWN',
                   'RECONCILING', 'CANCELLED')
    )
);

CREATE INDEX IF NOT EXISTS idx_agent_runtime_effect_claimable
    ON agent_runtime.effect (status, lease_until, updated_at);
CREATE INDEX IF NOT EXISTS idx_agent_runtime_effect_operation
    ON agent_runtime.effect (operation_id, created_at);

CREATE TABLE IF NOT EXISTS agent_runtime.outbox (
    event_id VARCHAR(128) PRIMARY KEY,
    source VARCHAR(64) NOT NULL,
    aggregate_type VARCHAR(64) NOT NULL,
    aggregate_id VARCHAR(128) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    payload JSONB NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    lease_owner VARCHAR(128),
    lease_until TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    dead_lettered_at TIMESTAMPTZ,
    last_error VARCHAR(1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- The table predates the delivery worker. Keep the migration idempotent for
-- databases that already created the v1 table.
ALTER TABLE agent_runtime.outbox
    ADD COLUMN IF NOT EXISTS dead_lettered_at TIMESTAMPTZ;

-- event_id is a transport identifier. The aggregate revision is the runtime
-- fact identity, so retries with a newly generated event_id must collapse too.
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_runtime_outbox_semantic
    ON agent_runtime.outbox (
        source, aggregate_type, aggregate_id, aggregate_version,
        (COALESCE(payload ->> 'event_type', ''))
    );

CREATE INDEX IF NOT EXISTS idx_agent_runtime_outbox_claimable
    ON agent_runtime.outbox (next_attempt_at, lease_until, created_at)
    WHERE published_at IS NULL;

INSERT INTO agent_runtime.schema_migration(version)
VALUES ('agent_runtime_core_v1')
ON CONFLICT (version) DO NOTHING;

INSERT INTO agent_runtime.schema_migration(version)
VALUES ('agent_runtime_outbox_delivery_v2')
ON CONFLICT (version) DO NOTHING;
