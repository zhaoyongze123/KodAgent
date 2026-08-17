-- 项目插件驱动的 Agent 数据库契约。
--
-- KodCloud 项目、任务、成员和资料仍是唯一业务事实源。本文件只保存：
-- 1. OA 用户与 KodCloud 用户的显式映射；
-- 2. 报告的短期受控二进制快照；
-- 3. 可失效的项目资料检索副本和同步审计。
-- 不保存 KodCloud accessToken、公开下载链接、文件路径或用户会话。

CREATE TABLE IF NOT EXISTS agent_kod_user_binding (
    tenant_id BIGINT NOT NULL,
    oa_user_id BIGINT NOT NULL,
    kod_user_id BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, oa_user_id),
    CONSTRAINT ck_agent_kod_user_binding_status CHECK (status IN ('ACTIVE', 'DISABLED'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_kod_user_binding_kod_user
    ON agent_kod_user_binding (tenant_id, kod_user_id);

-- 每个租户最多绑定一个共享制度目录和一个只读 KodCloud 服务账号。
-- 制度目录不是项目事实源，只作为管理员维护的检索副本来源；服务账号编号
-- 只用于让 KodCloud 重新执行目录权限校验，不保存 accessToken 或登录会话。
CREATE TABLE IF NOT EXISTS agent_policy_library_binding (
    tenant_id BIGINT PRIMARY KEY,
    kod_folder_id BIGINT NOT NULL,
    kod_service_user_id BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_policy_library_status CHECK (status IN ('ACTIVE', 'DISABLED')),
    CONSTRAINT ck_agent_policy_library_ids CHECK (kod_folder_id > 0 AND kod_service_user_id > 0)
);

-- 生成报告时保存同一份 ProjectAnalysisResult 和两种格式，确保卡片、DOCX、
-- Excel 不会因为导出时再次查询而出现数字不一致。
CREATE TABLE IF NOT EXISTS agent_project_report (
    report_id VARCHAR(64) PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    owner_user_id BIGINT NOT NULL,
    project_id BIGINT NOT NULL,
    analysis_data JSONB NOT NULL,
    docx_data BYTEA NOT NULL,
    xlsx_data BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_agent_project_report_expiry CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_agent_project_report_owner_expiry
    ON agent_project_report (tenant_id, owner_user_id, expires_at DESC);

-- 通用知识来源模型。POLICY_LIBRARY 由管理员绑定共享制度目录；PROJECT_FILES
-- 由 project_id + KodCloud file_id 绑定，二者均不保存可道云文件路径和令牌。
CREATE TABLE IF NOT EXISTS agent_knowledge_source (
    source_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    project_id BIGINT,
    kod_file_id BIGINT,
    display_name VARCHAR(500) NOT NULL,
    document_type VARCHAR(64) NOT NULL,
    content_hash VARCHAR(128),
    content_version VARCHAR(128),
    extraction_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    indexed_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    last_error_code VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_knowledge_source_type CHECK (source_type IN ('POLICY_LIBRARY', 'PROJECT_FILES')),
    CONSTRAINT ck_agent_knowledge_source_status CHECK (extraction_status IN ('PENDING', 'READY', 'UNSUPPORTED', 'NEEDS_OCR', 'FAILED', 'INVALIDATED')),
    CONSTRAINT ck_agent_knowledge_project_file CHECK (
        (source_type = 'PROJECT_FILES' AND project_id IS NOT NULL AND kod_file_id IS NOT NULL)
        OR (source_type = 'POLICY_LIBRARY' AND project_id IS NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_knowledge_project_source
    ON agent_knowledge_source (tenant_id, source_type, project_id, kod_file_id)
    WHERE source_type = 'PROJECT_FILES';

-- 统一知识源管理。目录源保存稳定 sourceID；本地上传源保存受控二进制。
-- 两者都不保存 KodCloud 路径、公开下载链接、浏览器令牌或 accessToken。
CREATE TABLE IF NOT EXISTS agent_knowledge_library (
    library_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    name VARCHAR(200) NOT NULL,
    source_kind VARCHAR(32) NOT NULL,
    kod_folder_id BIGINT,
    owner_user_id BIGINT NOT NULL,
    access_mode VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    last_sync_at TIMESTAMPTZ,
    last_sync_status VARCHAR(32),
    last_error_code VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_knowledge_library_kind CHECK (source_kind IN ('KOD_FOLDER', 'LOCAL_UPLOAD')),
    CONSTRAINT ck_agent_knowledge_library_access CHECK (
        (source_kind = 'KOD_FOLDER' AND access_mode = 'FOLDER' AND kod_folder_id IS NOT NULL)
        OR (source_kind = 'LOCAL_UPLOAD' AND access_mode IN ('ALL', 'CUSTOM') AND kod_folder_id IS NULL)
    ),
    CONSTRAINT ck_agent_knowledge_library_status CHECK (status IN ('ACTIVE', 'DISABLED'))
);
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_library_tenant
    ON agent_knowledge_library (tenant_id, status, source_kind, updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_knowledge_library_acl (
    library_id BIGINT NOT NULL REFERENCES agent_knowledge_library(library_id) ON DELETE CASCADE,
    subject_type VARCHAR(16) NOT NULL,
    subject_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (library_id, subject_type, subject_id),
    CONSTRAINT ck_agent_knowledge_library_acl_subject CHECK (subject_type IN ('USER', 'DEPARTMENT')),
    CONSTRAINT ck_agent_knowledge_library_acl_id CHECK (subject_id > 0)
);
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_library_acl_subject
    ON agent_knowledge_library_acl (subject_type, subject_id, library_id);

CREATE TABLE IF NOT EXISTS agent_knowledge_upload (
    library_id BIGINT PRIMARY KEY REFERENCES agent_knowledge_library(library_id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    mime_type VARCHAR(200) NOT NULL,
    content_data BYTEA NOT NULL,
    content_hash VARCHAR(128) NOT NULL,
    content_version VARCHAR(128) NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_knowledge_upload_size CHECK (size_bytes > 0)
);

ALTER TABLE agent_knowledge_source ADD COLUMN IF NOT EXISTS library_id BIGINT;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'agent_knowledge_source'::regclass
          AND conname = 'fk_agent_knowledge_source_library'
    ) THEN
        ALTER TABLE agent_knowledge_source ADD CONSTRAINT fk_agent_knowledge_source_library
            FOREIGN KEY (library_id) REFERENCES agent_knowledge_library(library_id) ON DELETE CASCADE;
    END IF;
END $$;
ALTER TABLE agent_knowledge_source DROP CONSTRAINT IF EXISTS ck_agent_knowledge_source_type;
ALTER TABLE agent_knowledge_source ADD CONSTRAINT ck_agent_knowledge_source_type
    CHECK (source_type IN ('POLICY_LIBRARY', 'PROJECT_FILES', 'KOD_FOLDER', 'LOCAL_UPLOAD'));
ALTER TABLE agent_knowledge_source DROP CONSTRAINT IF EXISTS ck_agent_knowledge_project_file;
ALTER TABLE agent_knowledge_source ADD CONSTRAINT ck_agent_knowledge_project_file CHECK (
    (source_type = 'PROJECT_FILES' AND project_id IS NOT NULL AND kod_file_id IS NOT NULL AND library_id IS NULL)
    OR (source_type = 'POLICY_LIBRARY' AND project_id IS NULL AND library_id IS NULL)
    OR (source_type = 'KOD_FOLDER' AND project_id IS NULL AND kod_file_id IS NOT NULL AND library_id IS NOT NULL)
    OR (source_type = 'LOCAL_UPLOAD' AND project_id IS NULL AND kod_file_id IS NULL AND library_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_knowledge_library_folder_file
    ON agent_knowledge_source (tenant_id, library_id, kod_file_id)
    WHERE source_type = 'KOD_FOLDER';
CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_knowledge_library_upload
    ON agent_knowledge_source (tenant_id, library_id)
    WHERE source_type = 'LOCAL_UPLOAD';

CREATE TABLE IF NOT EXISTS agent_knowledge_document (
    document_id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES agent_knowledge_source(source_id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    content_hash VARCHAR(128) NOT NULL,
    extraction_status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_id, content_hash)
);

CREATE TABLE IF NOT EXISTS agent_knowledge_chunk (
    chunk_id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES agent_knowledge_document(document_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    section VARCHAR(500),
    content TEXT NOT NULL,
    content_hash VARCHAR(128) NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (document_id, ordinal),
    UNIQUE (document_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_chunk_search
    ON agent_knowledge_chunk USING GIN (search_vector);

-- RAG 向量是全文索引的补充，不是另一份知识事实源。pgvector 不可用时，
-- 整个表和索引不会创建，Java 会继续使用全文检索并保持功能可用。
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')
            AND EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
        BEGIN
            CREATE EXTENSION IF NOT EXISTS vector;
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'pgvector is available but this migration role cannot enable it; project knowledge remains keyword-only';
        END;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        BEGIN
        CREATE TABLE IF NOT EXISTS agent_knowledge_chunk_embedding (
            chunk_id BIGINT PRIMARY KEY REFERENCES agent_knowledge_chunk(chunk_id) ON DELETE CASCADE,
            content_hash VARCHAR(128) NOT NULL,
            embedding_model VARCHAR(300) NOT NULL,
            embedding_projected vector(1536),
            status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            next_retry_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_error_code VARCHAR(128),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_agent_knowledge_embedding_status CHECK (status IN ('PENDING', 'PROCESSING', 'READY', 'FAILED')),
            CONSTRAINT ck_agent_knowledge_embedding_attempt CHECK (attempt_count >= 0)
        );
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'pgvector is installed but this migration role cannot create the optional embedding table; project knowledge remains keyword-only';
        END;

        IF to_regclass('agent_knowledge_chunk_embedding') IS NOT NULL THEN
            BEGIN
        CREATE INDEX IF NOT EXISTS idx_agent_knowledge_embedding_pending
            ON agent_knowledge_chunk_embedding (status, next_retry_at, updated_at);
        CREATE INDEX IF NOT EXISTS idx_agent_knowledge_embedding_hnsw
            ON agent_knowledge_chunk_embedding USING hnsw (embedding_projected vector_cosine_ops)
            WHERE status = 'READY' AND embedding_projected IS NOT NULL;
            EXCEPTION WHEN insufficient_privilege OR undefined_object OR feature_not_supported THEN
                RAISE NOTICE 'project embedding table is available but optional indexes could not be created; semantic retrieval stays disabled until migration succeeds';
            END;
        END IF;
    ELSE
        RAISE NOTICE 'pgvector is not installed; project knowledge remains keyword-only';
    END IF;
END $$;

-- 同步记录仅保留版本、状态与安全错误码。正文、文件路径和令牌一律不进审计。
CREATE TABLE IF NOT EXISTS agent_project_document_sync (
    sync_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    project_id BIGINT NOT NULL,
    requested_by_user_id BIGINT,
    mode VARCHAR(16) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    scanned_count INTEGER NOT NULL DEFAULT 0,
    indexed_count INTEGER NOT NULL DEFAULT 0,
    invalidated_count INTEGER NOT NULL DEFAULT 0,
    error_code VARCHAR(128),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_project_document_sync_mode CHECK (mode IN ('INCREMENTAL', 'MANUAL')),
    CONSTRAINT ck_agent_project_document_sync_status CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'))
);
CREATE INDEX IF NOT EXISTS idx_agent_project_document_sync_scope
    ON agent_project_document_sync (tenant_id, project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_project_analysis_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    project_id BIGINT NOT NULL,
    action VARCHAR(32) NOT NULL,
    snapshot_at TIMESTAMPTZ,
    statistics_rule_version VARCHAR(64) NOT NULL,
    source_versions JSONB NOT NULL DEFAULT '[]'::jsonb,
    retrieval_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_id VARCHAR(64),
    failure_code VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_agent_project_analysis_audit_action CHECK (action IN ('ANALYZE', 'REPORT', 'SEARCH', 'SYNC'))
);
ALTER TABLE agent_project_analysis_audit
    ADD COLUMN IF NOT EXISTS retrieval_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS idx_agent_project_analysis_audit_scope
    ON agent_project_analysis_audit (tenant_id, user_id, project_id, created_at DESC);

INSERT INTO agent_schema_migration (version)
VALUES ('agent_project_provider_v1')
ON CONFLICT (version) DO NOTHING;

INSERT INTO agent_schema_migration (version)
VALUES ('agent_project_hybrid_rag_v1')
ON CONFLICT (version) DO NOTHING;

INSERT INTO agent_schema_migration (version)
VALUES ('agent_knowledge_source_management_v1')
ON CONFLICT (version) DO NOTHING;

COMMENT ON TABLE agent_kod_user_binding IS 'OA 到 KodCloud 的显式用户映射；缺少映射必须返回 KOD_USER_BINDING_REQUIRED';
COMMENT ON TABLE agent_policy_library_binding IS '管理员维护的共享制度目录与只读服务账号绑定，不保存 KodCloud 凭据';
COMMENT ON TABLE agent_project_report IS '当前用户可下载的短期项目报告快照，下载时重新检查 owner';
COMMENT ON TABLE agent_knowledge_source IS '通用项目/制度知识来源，不保存文件路径、下载 URL 或登录凭据';
COMMENT ON TABLE agent_knowledge_library IS '管理员维护的目录或本地上传知识源；目录仅保存稳定 sourceID，本地上传受 ACL 约束';
COMMENT ON TABLE agent_knowledge_upload IS '管理员上传知识源的受控二进制；不提供公开下载地址';
COMMENT ON TABLE agent_project_analysis_audit IS '项目 Agent 审计，仅保存版本、口径和错误码，不保存文件正文';

DO $$
BEGIN
    IF to_regclass('agent_knowledge_chunk_embedding') IS NOT NULL THEN
        EXECUTE 'COMMENT ON TABLE agent_knowledge_chunk_embedding IS ''项目资料的可失效语义检索副本；正文、路径、令牌均不保存于此表''';
    END IF;
END $$;
