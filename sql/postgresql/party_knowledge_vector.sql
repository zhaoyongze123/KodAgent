-- pgvector upgrade for SiliconFlow Qwen/Qwen3-VL-Embedding-8B (4096 dimensions).
-- The 1536-dimensional deterministic projection is the HNSW retrieval index;
-- the original 4096-dimensional vector stays available for diagnostics and
-- future exact reranking. This migration is idempotent.
DO $$
DECLARE
    embedding_type TEXT;
    projected_type TEXT;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
        CREATE EXTENSION IF NOT EXISTS vector;
        ALTER TABLE knowledge_chunk ADD COLUMN IF NOT EXISTS embedding vector(4096);
        ALTER TABLE knowledge_chunk ADD COLUMN IF NOT EXISTS embedding_projected vector(1536);
        SELECT format_type(a.atttypid, a.atttypmod) INTO embedding_type
        FROM pg_attribute a
        WHERE a.attrelid = 'knowledge_chunk'::regclass AND a.attname = 'embedding' AND NOT a.attisdropped;
        SELECT format_type(a.atttypid, a.atttypmod) INTO projected_type
        FROM pg_attribute a
        WHERE a.attrelid = 'knowledge_chunk'::regclass AND a.attname = 'embedding_projected' AND NOT a.attisdropped;
        -- A dimension migration cannot preserve vectors safely. Clear both
        -- related columns as one unit so query/index representations never
        -- describe different source embeddings.
        IF embedding_type <> 'vector(4096)' OR projected_type <> 'vector(1536)' THEN
            DROP INDEX IF EXISTS idx_knowledge_chunk_embedding_projected;
            UPDATE knowledge_chunk SET embedding = NULL, embedding_projected = NULL;
            ALTER TABLE knowledge_chunk ALTER COLUMN embedding TYPE vector(4096) USING embedding::vector(4096);
            ALTER TABLE knowledge_chunk ALTER COLUMN embedding_projected TYPE vector(1536) USING embedding_projected::vector(1536);
        END IF;
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunk_embedding_projected
            ON knowledge_chunk USING hnsw (embedding_projected vector_cosine_ops)
            WHERE embedding_projected IS NOT NULL;
        INSERT INTO agent_schema_migration (version)
        VALUES ('agent_party_knowledge_vector_v1')
        ON CONFLICT (version) DO NOTHING;
        -- pgvector HNSW/IVFFlat indexes cap dimensions at 2000. The selected
        -- Qwen model returns 4096 dimensions, so the projected 1536-dim column
        -- is indexed while the full vector remains available for reranking.
    ELSE
        RAISE NOTICE 'pgvector is not installed; keyword retrieval remains active';
    END IF;
END $$;
