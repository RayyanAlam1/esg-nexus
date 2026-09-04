-- Enables pgvector so knowledge_chunks.embedding can be migrated to a native vector column when an
-- embedding provider is configured (see docs/RAG.md).
CREATE EXTENSION IF NOT EXISTS vector;
