"""Agentic RAG retrieval: index search → permission filter → metadata filter → rerank → citations."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.rag.index import get_index, tokenize
from app.core.security import Principal
from app.models.ai import KnowledgeChunk, KnowledgeDocument


@dataclass
class Hit:
    chunk_id: int
    document_code: str
    document_title: str
    kind: str
    text: str
    score: float
    meta: dict
    version: str
    freshness: str | None

    @property
    def citation(self) -> str:
        page = self.meta.get("printed_pages") or self.meta.get("pdf_page")
        if self.kind == "report" and page:
            return f"[{self.document_code} p.{page}]"
        for key in ("requirement_code", "metric_code", "policy_code", "rule_code"):
            if self.meta.get(key):
                return f"[{self.meta[key]}]"
        return f"[{self.document_code}#{self.meta.get('chunk_index', self.chunk_id)}]"

    def as_dict(self) -> dict:
        return {
            "citation": self.citation,
            "document": self.document_code,
            "title": self.document_title,
            "kind": self.kind,
            "score": round(self.score, 3),
            "text": self.text[:900],
            "meta": self.meta,
            "version": self.version,
            "freshness": self.freshness,
        }


def _allowed(doc: KnowledgeDocument, principal: Principal) -> bool:
    roles = (doc.permissions or {}).get("roles", ["*"])
    return "*" in roles or bool(set(roles) & set(principal.roles))


def retrieve(db: Session, principal: Principal, query: str, *, limit: int = 6, kind: str | None = None, rerank: bool = True) -> list[Hit]:
    index = get_index(db, principal.tenant_id)
    candidates = index.search(query, limit=max(limit * 5, 30))
    if not candidates:
        return []
    ids = [cid for cid, _ in candidates]
    chunks = {c.id: c for c in db.execute(select(KnowledgeChunk).where(KnowledgeChunk.id.in_(ids))).scalars().all()}
    docs: dict[int, KnowledgeDocument] = {}
    hits: list[Hit] = []
    qtokens = set(tokenize(query))
    for cid, score in candidates:
        chunk = chunks.get(cid)
        if chunk is None:
            continue
        doc = docs.get(chunk.document_id) or db.get(KnowledgeDocument, chunk.document_id)
        docs[chunk.document_id] = doc
        if doc is None or doc.tenant_id != principal.tenant_id or doc.status != "approved":
            continue
        if not _allowed(doc, principal):
            continue  # permission-aware RAG
        if kind and doc.kind != kind:
            continue
        final = score
        if rerank:
            # lightweight rerank: coverage of query terms + exact code matches + freshness bias
            toks = set(tokenize(chunk.text))
            coverage = len(qtokens & toks) / (len(qtokens) or 1)
            exact = 1.0 if any(q.upper() in chunk.text for q in query.split() if "." in q) else 0.0
            final = score * (1 + coverage) + 2 * exact
        hits.append(
            Hit(
                chunk.id,
                doc.code,
                doc.title,
                doc.kind,
                chunk.text,
                final,
                {**(chunk.meta or {}), "chunk_index": chunk.chunk_index},
                doc.version,
                doc.freshness_date.isoformat() if doc.freshness_date else None,
            )
        )
    hits.sort(key=lambda h: -h.score)
    return hits[:limit]
