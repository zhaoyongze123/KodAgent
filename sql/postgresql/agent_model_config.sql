-- Agent 模型供应商、凭证、模型和绑定配置。
-- API Key 只保存密文，明文仅在内部 resolve 接口返回给受信任的 Python Agent。
CREATE TABLE IF NOT EXISTS agent_model_provider (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    provider_type VARCHAR(40) NOT NULL DEFAULT 'OPENAI_COMPATIBLE',
    base_url VARCHAR(500) NOT NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'CUSTOM',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, name)
);

-- Upgrade path for environments that created the provider table before the
-- model settings contract was centralized in this migration.
ALTER TABLE agent_model_provider ADD COLUMN IF NOT EXISTS provider_type VARCHAR(40) NOT NULL DEFAULT 'OPENAI_COMPATIBLE';
ALTER TABLE agent_model_provider ADD COLUMN IF NOT EXISTS base_url VARCHAR(500);
ALTER TABLE agent_model_provider ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'CUSTOM';
ALTER TABLE agent_model_provider ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE agent_model_provider ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agent_model_provider ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE agent_model_provider ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

COMMENT ON TABLE agent_model_provider IS 'Agent 模型供应商配置';
COMMENT ON COLUMN agent_model_provider.provider_type IS '供应商协议类型，当前支持 OPENAI_COMPATIBLE';
COMMENT ON COLUMN agent_model_provider.source IS '供应商来源，BUILTIN 或 CUSTOM';

CREATE TABLE IF NOT EXISTS agent_model_credential (
    id BIGSERIAL PRIMARY KEY,
    provider_id BIGINT NOT NULL REFERENCES agent_model_provider(id),
    api_key_ciphertext TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
    last_test_at TIMESTAMP NULL,
    last_error VARCHAR(1000) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider_id)
);
ALTER TABLE agent_model_credential ADD COLUMN IF NOT EXISTS api_key_ciphertext TEXT;
ALTER TABLE agent_model_credential ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN';
ALTER TABLE agent_model_credential ADD COLUMN IF NOT EXISTS last_test_at TIMESTAMP;
ALTER TABLE agent_model_credential ADD COLUMN IF NOT EXISTS last_error VARCHAR(1000);
ALTER TABLE agent_model_credential ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE agent_model_credential ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

COMMENT ON TABLE agent_model_credential IS 'Agent 模型供应商凭证，API Key 使用 AES 密文保存';

CREATE TABLE IF NOT EXISTS agent_model (
    id BIGSERIAL PRIMARY KEY,
    provider_id BIGINT NOT NULL REFERENCES agent_model_provider(id),
    model_name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NULL,
    capabilities JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    source VARCHAR(20) NOT NULL DEFAULT 'SYNCED',
    last_synced_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider_id, model_name)
);
ALTER TABLE agent_model ADD COLUMN IF NOT EXISTS display_name VARCHAR(255);
ALTER TABLE agent_model ADD COLUMN IF NOT EXISTS capabilities JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE agent_model ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE agent_model ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'SYNCED';
ALTER TABLE agent_model ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP;
ALTER TABLE agent_model ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE agent_model ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

COMMENT ON TABLE agent_model IS 'Agent 可调用模型清单';
COMMENT ON COLUMN agent_model.capabilities IS '模型能力探测结果，例如 tools、streaming、vision、contextWindow';

CREATE TABLE IF NOT EXISTS agent_model_binding (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    user_id BIGINT NULL,
    agent_name VARCHAR(100) NOT NULL,
    model_id BIGINT NOT NULL REFERENCES agent_model(id),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, user_id, agent_name)
);
ALTER TABLE agent_model_binding ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE agent_model_binding ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE agent_model_binding ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE agent_model_binding ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

COMMENT ON TABLE agent_model_binding IS 'Agent、租户和用户的模型绑定；user_id 为空表示租户默认';

CREATE INDEX IF NOT EXISTS idx_agent_model_provider_tenant ON agent_model_provider(tenant_id, enabled);
CREATE INDEX IF NOT EXISTS idx_agent_model_provider_enabled ON agent_model(provider_id, enabled);
CREATE INDEX IF NOT EXISTS idx_agent_model_binding_lookup ON agent_model_binding(tenant_id, user_id, agent_name, enabled);

INSERT INTO agent_schema_migration (version)
VALUES ('agent_model_config_v1')
ON CONFLICT (version) DO NOTHING;
