"""Retrieval indexes (adapter pattern).

- LexicalIndex: in-process BM25 over KnowledgeChunk rows — no external service, works air-gapped.
- PgVectorIndex: extension point for pgvector cosine search when an embedding provider is configured.
Both return (chunk_id, score) pairs; permission filtering happens in the retriever.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai import KnowledgeChunk, KnowledgeDocument

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\.\-]*")
STOP = set(
    [
        "the",
        "a",
        "an",
        "of",
        "and",
        "or",
        "to",
        "in",
        "for",
        "on",
        "by",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "as",
        "at",
        "from",
        "that",
        "this",
        "it",
        "its",
        "their",
        "our",
        "we",
        "they",
        "which",
        "what",
        "how",
        "why",
        "when",
        "where",
        "than",
        "into",
        "per",
        "vs",
    ]
)


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOP and len(t) > 1]


class Index(Protocol):
    def search(self, query: str, *, limit: int = 20) -> list[tuple[int, float]]: ...


@dataclass
class _Doc:
    chunk_id: int
    tokens: list[str]
    length: int


class LexicalIndex:
    """BM25 (k1=1.5, b=0.75) built lazily per tenant and refreshed when chunk count changes."""

    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.docs: list[_Doc] = []
        self.df: Counter = Counter()
        self.avgdl = 1.0
        self._build()

    def _build(self) -> None:
        rows = self.db.execute(
            select(KnowledgeChunk.id, KnowledgeChunk.text)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(KnowledgeDocument.tenant_id == self.tenant_id, KnowledgeDocument.status == "approved")
        ).all()
        self.docs = []
        self.df = Counter()
        for cid, text in rows:
            toks = tokenize(text)
            self.docs.append(_Doc(cid, toks, len(toks)))
            for t in set(toks):
                self.df[t] += 1
        self.avgdl = (sum(d.length for d in self.docs) / len(self.docs)) if self.docs else 1.0
        self.n = len(self.docs)
        self._tf = {d.chunk_id: Counter(d.tokens) for d in self.docs}

    def search(self, query: str, *, limit: int = 20) -> list[tuple[int, float]]:
        q = tokenize(query)
        if not q or not self.docs:
            return []
        k1, b = 1.5, 0.75
        scores: dict[int, float] = defaultdict(float)
        for term in set(q):
            df = self.df.get(term)
            if not df:
                continue
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            for d in self.docs:
                tf = self._tf[d.chunk_id].get(term)
                if not tf:
                    continue
                denom = tf + k1 * (1 - b + b * d.length / self.avgdl)
                scores[d.chunk_id] += idf * tf * (k1 + 1) / denom
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return ranked[:limit]


class PgVectorIndex:
    """Adapter for pgvector. Requires `embedding` populated on knowledge_chunks and an embedding provider.

    Implementation note: with PostgreSQL + pgvector, replace `search` with
    `SELECT id, 1 - (embedding <=> :q) AS score FROM knowledge_chunks ORDER BY embedding <=> :q LIMIT :k`.
    Kept as an explicit extension point so the retrieval strategy is swappable without touching agents.
    """

    def __init__(self, db: Session, tenant_id: int, embed):
        self.db, self.tenant_id, self.embed = db, tenant_id, embed

    def search(self, query: str, *, limit: int = 20) -> list[tuple[int, float]]:
        qv = self.embed(query)
        rows = self.db.execute(
            select(KnowledgeChunk.id, KnowledgeChunk.embedding)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(KnowledgeDocument.tenant_id == self.tenant_id, KnowledgeChunk.embedding.isnot(None))
        ).all()
        scored = []
        for cid, emb in rows:
            if not emb:
                continue
            dot = sum(a * b for a, b in zip(qv, emb, strict=False))
            na = math.sqrt(sum(a * a for a in qv)) or 1.0
            nb = math.sqrt(sum(b * b for b in emb)) or 1.0
            scored.append((cid, dot / (na * nb)))
        scored.sort(key=lambda x: -x[1])
        return scored[:limit]


_INDEX_CACHE: dict[int, tuple[int, LexicalIndex]] = {}


def get_index(db: Session, tenant_id: int) -> LexicalIndex:
    count = (
        db.execute(select(KnowledgeChunk.id).join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id).where(KnowledgeDocument.tenant_id == tenant_id))
        .all()
        .__len__()
    )
    cached = _INDEX_CACHE.get(tenant_id)
    if cached and cached[0] == count:
        cached[1].db = db
        return cached[1]
    idx = LexicalIndex(db, tenant_id)
    _INDEX_CACHE[tenant_id] = (count, idx)
    return idx
