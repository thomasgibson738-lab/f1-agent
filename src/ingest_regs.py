"""Parse FIA regulation PDFs, chunk them, embed via Voyage, store in LanceDB.

Run from the project root:
    python src/ingest_regs.py

Idempotent: overwrites the LanceDB table on each run.
"""

from pathlib import Path

import lancedb
import pymupdf
import voyageai
from dotenv import load_dotenv

load_dotenv()

REGS_DIR = Path("data/regs")
DB_PATH = "data/regs.lance"
TABLE_NAME = "regulations"

CHUNK_SIZE = 2000  # characters (~500 English tokens)
OVERLAP = 200

EMBED_MODEL = "voyage-3"
BATCH_SIZE = 32  # texts per Voyage embed call (keeps total tokens well under limits)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = OVERLAP):
    """Yield fixed-window chunks with overlap. Skips empty/whitespace chunks."""
    if not text.strip():
        return
    step = size - overlap
    for i in range(0, len(text), step):
        chunk = text[i : i + size]
        if chunk.strip():
            yield chunk
        if i + size >= len(text):
            break


def extract_chunks(pdf_path: Path) -> list[dict]:
    """Extract per-page chunks with metadata for one PDF."""
    doc = pymupdf.open(pdf_path)
    out: list[dict] = []
    for page_num in range(doc.page_count):
        page = doc[page_num]
        text = page.get_text()
        for idx, chunk in enumerate(chunk_text(text)):
            out.append(
                {
                    "id": f"{pdf_path.stem}::p{page_num + 1}::c{idx}",
                    "text": chunk,
                    "source": pdf_path.name,
                    "page": page_num + 1,
                    "chunk_idx": idx,
                }
            )
    doc.close()
    return out


def embed_chunks(chunks: list[dict], vo: voyageai.Client) -> list[dict]:
    """Embed chunks in batches, attach 'vector' to each dict."""
    texts = [c["text"] for c in chunks]
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        result = vo.embed(batch, model=EMBED_MODEL, input_type="document")
        all_embeddings.extend(result.embeddings)
        print(f"  Embedded {i + len(batch)} / {len(texts)}")
    for c, vec in zip(chunks, all_embeddings):
        c["vector"] = vec
    return chunks


def main() -> None:
    pdfs = sorted(REGS_DIR.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in {REGS_DIR.resolve()}")

    print(f"Found {len(pdfs)} PDF(s) in {REGS_DIR}/")
    all_chunks: list[dict] = []
    for pdf in pdfs:
        print(f"Parsing {pdf.name}...")
        chunks = extract_chunks(pdf)
        print(f"  {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"\nTotal chunks across all PDFs: {len(all_chunks)}")

    print(f"\nEmbedding with model '{EMBED_MODEL}' (batch size {BATCH_SIZE})...")
    vo = voyageai.Client()  # reads VOYAGE_API_KEY from env
    all_chunks = embed_chunks(all_chunks, vo)

    print(f"\nWriting to {DB_PATH} (table: {TABLE_NAME}, mode=overwrite)...")
    db = lancedb.connect(DB_PATH)
    table = db.create_table(TABLE_NAME, data=all_chunks, mode="overwrite")

    print(f"\nDone. {table.count_rows()} rows in '{TABLE_NAME}'.")


if __name__ == "__main__":
    main()
