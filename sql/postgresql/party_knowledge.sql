-- Employee-visible party-file knowledge retrieval schema.
-- This store contains derived text only. Source file paths, storage URLs and
-- audience definitions remain in OA and are never copied to this database.

CREATE TABLE IF NOT EXISTS knowledge_document (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    source_party_file_id BIGINT NOT NULL,
    title VARCHAR(500) NOT NULL,
    document_type VARCHAR(64) NOT NULL,
    content_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'READY',
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, source_party_file_id, content_hash)
);
ALTER TABLE knowledge_document ADD COLUMN IF NOT EXISTS tenant_id BIGINT;
ALTER TABLE knowledge_document ADD COLUMN IF NOT EXISTS source_party_file_id BIGINT;
ALTER TABLE knowledge_document ADD COLUMN IF NOT EXISTS title VARCHAR(500);
ALTER TABLE knowledge_document ADD COLUMN IF NOT EXISTS document_type VARCHAR(64);
ALTER TABLE knowledge_document ADD COLUMN IF NOT EXISTS content_hash VARCHAR(128);
ALTER TABLE knowledge_document ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'READY';
ALTER TABLE knowledge_document ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;
ALTER TABLE knowledge_document ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE knowledge_document ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS knowledge_chunk (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES knowledge_document(id) ON DELETE CASCADE,
    section VARCHAR(500),
    ordinal INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(128) NOT NULL,
    search_vector TSVECTOR,
    status VARCHAR(32) NOT NULL DEFAULT 'READY',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (document_id, ordinal),
    UNIQUE (document_id, content_hash)
);
ALTER TABLE knowledge_chunk ADD COLUMN IF NOT EXISTS section VARCHAR(500);
ALTER TABLE knowledge_chunk ADD COLUMN IF NOT EXISTS ordinal INTEGER;
ALTER TABLE knowledge_chunk ADD COLUMN IF NOT EXISTS content TEXT;
ALTER TABLE knowledge_chunk ADD COLUMN IF NOT EXISTS content_hash VARCHAR(128);
ALTER TABLE knowledge_chunk ADD COLUMN IF NOT EXISTS search_vector TSVECTOR;
ALTER TABLE knowledge_chunk ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'READY';
ALTER TABLE knowledge_chunk ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE knowledge_chunk ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS knowledge_fact (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES knowledge_document(id) ON DELETE CASCADE,
    chunk_id BIGINT REFERENCES knowledge_chunk(id) ON DELETE SET NULL,
    fact_type VARCHAR(64) NOT NULL,
    subject VARCHAR(500),
    action VARCHAR(500),
    responsible_party VARCHAR(500),
    deadline VARCHAR(255),
    condition TEXT,
    required_material VARCHAR(1000),
    fact_key VARCHAR(255) NOT NULL,
    fact_value TEXT NOT NULL,
    confidence NUMERIC(5, 4),
    status VARCHAR(32) NOT NULL DEFAULT 'READY',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS chunk_id BIGINT;
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS fact_type VARCHAR(64);
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS subject VARCHAR(500);
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS action VARCHAR(500);
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS responsible_party VARCHAR(500);
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS deadline VARCHAR(255);
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS condition TEXT;
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS required_material VARCHAR(1000);
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS fact_key VARCHAR(255);
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS fact_value TEXT;
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS confidence NUMERIC(5, 4);
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'READY';
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS knowledge_ingest_job (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    source_party_file_id BIGINT NOT NULL,
    requested_by_user_id BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    content_hash VARCHAR(128),
    error_code VARCHAR(128),
    error_message VARCHAR(1000),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_knowledge_document_tenant_source_status
    ON knowledge_document (tenant_id, source_party_file_id, status, id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_document_status_ordinal
    ON knowledge_chunk (document_id, status, ordinal, id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_search_vector
    ON knowledge_chunk USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_knowledge_fact_document_status
    ON knowledge_fact (document_id, status, fact_type, fact_key);
CREATE INDEX IF NOT EXISTS idx_knowledge_ingest_job_scope_status
    ON knowledge_ingest_job (tenant_id, source_party_file_id, status, created_at);

INSERT INTO agent_schema_migration (version)
VALUES ('agent_party_knowledge_v1')
ON CONFLICT (version) DO NOTHING;

COMMENT ON TABLE knowledge_document IS '党务文件的受控知识文档；源文件权限仍由 OA PartyFileService 复核';
COMMENT ON TABLE knowledge_chunk IS '知识文档切片，只保存可向已授权用户返回的文本';
COMMENT ON TABLE knowledge_fact IS '从知识文档提取的结构化事实，供受控工作流使用';
COMMENT ON TABLE knowledge_ingest_job IS '党务知识导入任务状态，不保存源文件路径或存储凭据';
COMMENT ON COLUMN knowledge_document.source_party_file_id IS 'OA party_file 主键；查询时必须按当前用户可见性二次校验';
COMMENT ON COLUMN knowledge_ingest_job.error_message IS '可运维错误摘要，禁止写入文件 URL、路径、令牌或凭据';
