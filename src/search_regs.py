"""Search the FIA regulation embeddings in LanceDB.

Importable:
    from search_regs import search_regulations
    hits = search_regulations("minimum car weight", k=5)

Runnable for ad-hoc smoke testing:
    python src/search_regs.py "minimum car weight"
"""

from typing import Optional

import lancedb
import voyageai
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "data/regs.lance"
TABLE_NAME = "regulations"
EMBED_MODEL = "voyage-3"

# Lazy singletons so repeated calls in one process don't re-open the DB
# or rebuild the Voyage client.
_vo: Optional[voyageai.Client] = None
_table = None


def _get_vo() -> voyageai.Client:
    global _vo
    if _vo is None:
        _vo = voyageai.Client()
    return _vo


def _get_table():
    global _table
    if _table is None:
        db = lancedb.connect(DB_PATH)
        _table = db.open_table(TABLE_NAME)
    return _table


def search_regulations(query: str, k: int = 5) -> list[dict]:
    """Return top-k regulation chunks most similar to the query.

    Each result dict contains: text, source, page, chunk_idx, id, _distance.
    Lower _distance = closer match (cosine distance).
    """
    vo = _get_vo()
    table = _get_table()

    # input_type="query" tells Voyage this is a search query, not a
    # document being indexed — produces a different embedding optimized
    # for retrieval against documents embedded with input_type="document".
    embedded = vo.embed([query], model=EMBED_MODEL, input_type="query")
    query_vec = embedded.embeddings[0]

    return (
        table.search(query_vec)
        .metric("cosine")
        .limit(k)
        .to_list()
    )


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "what is the minimum weight of an F1 car"
    print(f"Query: {q}\n")

    hits = search_regulations(q, k=5)
    for i, hit in enumerate(hits, 1):
        dist = hit.get("_distance", float("nan"))
        snippet = hit["text"][:400] + ("..." if len(hit["text"]) > 400 else "")
        print(f"--- Result {i}  (cosine distance: {dist:.4f}) ---")
        print(f"Source: {hit['source']} | page {hit['page']} | chunk {hit['chunk_idx']}")
        print(snippet)
        print()
