"""Per-connection schema index — RAG over tables.

Given a DBAdapter, introspect the schema, embed one document per table, and
answer retrieve(query) with the top-k most relevant TableInfo objects.

Isolation: each connection_id gets its own Chroma collection. That way one
user's warehouse tables can't leak into another's retrieval.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.base import DBAdapter, TableInfo

from app.rag.embedder import Embedder


@dataclass
class RetrievedTable:
    table: "TableInfo"
    score: float  # cosine similarity — higher is better


def build_table_document(table: "TableInfo") -> str:
    """Compact, embedding-friendly description of a table.

    Format matters: we lead with the table name (users search for it),
    then column names in plain text so the embedder can key off them,
    then any human description.
    """
    schema_prefix = f"{table.schema}." if table.schema else ""
    parts = [f"Table: {schema_prefix}{table.name}"]
    if table.columns:
        col_words = ", ".join(f"{c.name} ({c.type.lower()})" for c in table.columns)
        parts.append(f"Columns: {col_words}")
    if table.description:
        parts.append(f"Description: {table.description}")
    return "\n".join(parts)


class SchemaIndex:
    """Chroma-backed schema retriever, one per connection.

    Uses an in-memory Chroma client so the index is process-local. For
    persistence we can swap in PersistentClient later — the API is identical.
    """

    def __init__(
        self,
        connection_id: str,
        embedder: Embedder,
        chroma_client=None,
    ):
        import chromadb

        self.connection_id = connection_id
        self.embedder = embedder
        self._client = chroma_client or chromadb.Client()
        # Chroma collection names must match ^[a-zA-Z0-9._-]{3,63}$ — sanitize.
        safe_name = _sanitize(connection_id)
        # If the collection already exists (e.g. re-index), start clean.
        try:
            self._client.delete_collection(name=safe_name)
        except Exception:
            pass
        self._collection = self._client.create_collection(
            name=safe_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._tables_by_id: dict[str, "TableInfo"] = {}

    async def index_schema(self, adapter: "DBAdapter") -> int:
        """Introspect the adapter and populate the index. Returns table count."""
        tables = await adapter.list_tables()
        if not tables:
            return 0

        docs = [build_table_document(t) for t in tables]
        ids = [_table_id(t) for t in tables]
        vectors = self.embedder.embed(docs)

        metadatas = [
            {
                "table_name": t.name,
                "schema": t.schema or "",
                "column_count": len(t.columns),
            }
            for t in tables
        ]

        self._collection.upsert(
            ids=ids,
            embeddings=vectors,
            documents=docs,
            metadatas=metadatas,
        )
        self._tables_by_id = dict(zip(ids, tables, strict=True))
        return len(tables)

    def retrieve(self, query: str, k: int = 5) -> list[RetrievedTable]:
        """Return the top-k tables ranked by relevance to the NL query."""
        if not self._tables_by_id:
            return []
        k = max(1, min(k, len(self._tables_by_id)))
        [query_vec] = self.embedder.embed([query])
        results = self._collection.query(
            query_embeddings=[query_vec],
            n_results=k,
        )
        hits: list[RetrievedTable] = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for tid, dist in zip(ids, distances, strict=True):
            table = self._tables_by_id.get(tid)
            if table is None:
                continue
            # Chroma returns cosine *distance* (1 - similarity). Convert.
            hits.append(RetrievedTable(table=table, score=1.0 - float(dist)))
        return hits

    def table_count(self) -> int:
        return len(self._tables_by_id)


def _table_id(table: "TableInfo") -> str:
    """Stable ID for the collection — schema-qualified table name."""
    return f"{table.schema}.{table.name}" if table.schema else table.name


def _sanitize(name: str) -> str:
    """Chroma collection names: 3-63 chars, [a-zA-Z0-9._-]."""
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    cleaned = "".join(c if c in allowed else "_" for c in name)
    if len(cleaned) < 3:
        cleaned = cleaned + "_pad"
    return cleaned[:63]
