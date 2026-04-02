"""
core/indexer.py — PDF 解析、chunking、embedding，寫入 ChromaDB。

Chunking 優先順序：
1. 依「第X條」條文邊界切割
2. 無明確條號時以 512 chars（≈tokens）固定切割，overlap 50
"""

import hashlib
import re
from pathlib import Path
from typing import Callable, Optional

import fitz  # PyMuPDF
import chromadb
from chromadb.utils import embedding_functions

CHROMA_DIR = Path("data/chroma_db")
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# 條文結構的正則：第X條（支援國字與阿拉伯數字）
_ARTICLE_PATTERN = re.compile(
    r"(?=第\s*[一二三四五六七八九十百千萬\d]+\s*條)"
)
_CHAPTER_PATTERN = re.compile(
    r"第\s*[一二三四五六七八九十百千萬\d]+\s*[章節]"
)
_ARTICLE_HEAD = re.compile(
    r"^第\s*[一二三四五六七八九十百千萬\d]+\s*條"
)


# ── ChromaDB 工廠 ─────────────────────────────────────────────


def _client() -> chromadb.PersistentClient:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def _embedding_fn() -> embedding_functions.SentenceTransformerEmbeddingFunction:
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )


def _safe_name(source_name: str) -> str:
    """將任意檔名轉為合法 ChromaDB collection name（ASCII + hash）。"""
    stem = Path(source_name).stem
    hash_suffix = hashlib.md5(source_name.encode()).hexdigest()[:8]
    ascii_part = re.sub(r"[^a-zA-Z0-9]", "_", stem).strip("_")
    prefix = ascii_part[:20] if len(ascii_part) >= 3 else "doc"
    return f"{prefix}_{hash_suffix}"


# ── PDF 解析 ──────────────────────────────────────────────────


def _extract_pages(pdf_path: str) -> list[dict]:
    """每頁提取文字，回傳 [{page, text}]。"""
    results = []
    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc):
        text = page.get_text("text")
        if text.strip():
            results.append({"page": i + 1, "text": text})
    doc.close()
    return results


# ── Chunking ──────────────────────────────────────────────────


def _detect_chapter(text: str) -> str:
    """從文字前段偵測所屬章節標題。"""
    m = _CHAPTER_PATTERN.search(text[:200])
    return m.group(0) if m else ""


def _chunk_by_articles(text: str, page: int) -> list[dict]:
    """依「第X條」邊界切割，保留章節與條號 metadata。"""
    parts = _ARTICLE_PATTERN.split(text)
    chunks = []
    for part in parts:
        part = part.strip()
        if len(part) < 15:
            continue
        m = _ARTICLE_HEAD.match(part)
        chunks.append({
            "text": part,
            "page": page,
            "chapter": _detect_chapter(part),
            "article": m.group(0) if m else "",
        })
    return chunks


def _chunk_fixed(
    text: str, page: int, chunk_size: int = 512, overlap: int = 50
) -> list[dict]:
    """固定大小切割（字元數近似 token 數）。"""
    chapter = _detect_chapter(text)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append({
                "text": piece,
                "page": page,
                "chapter": chapter,
                "article": "",
            })
        start += chunk_size - overlap
    return chunks


def _chunk_page(
    text: str, page: int, chunk_size: int = 512, overlap: int = 50
) -> list[dict]:
    """優先條文結構，fallback 固定切割。"""
    if _ARTICLE_PATTERN.search(text):
        chunks = _chunk_by_articles(text, page)
        if chunks:
            return chunks
    return _chunk_fixed(text, page, chunk_size, overlap)


# ── 主要 API ──────────────────────────────────────────────────


def index_pdf(
    pdf_path: str,
    source_name: str,
    chunk_size: int = 512,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """
    將 PDF 建索引並寫入 ChromaDB。

    Returns:
        {"chunks": int, "already_existed": bool}
    """
    client = _client()
    ef = _embedding_fn()
    coll_name = _safe_name(source_name)

    # 已建索引則跳過
    existing = [c.name for c in client.list_collections()]
    if coll_name in existing:
        col = client.get_collection(coll_name, embedding_function=ef)
        return {"chunks": col.count(), "already_existed": True}

    # 解析 PDF
    pages = _extract_pages(pdf_path)
    if not pages:
        return {"chunks": 0, "already_existed": False}

    # Chunking
    all_chunks: list[dict] = []
    for p in pages:
        for chunk in _chunk_page(p["text"], p["page"], chunk_size):
            chunk["source"] = source_name
            all_chunks.append(chunk)

    if not all_chunks:
        return {"chunks": 0, "already_existed": False}

    # 建 collection（cosine 距離）
    col = client.create_collection(
        name=coll_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine", "source_name": source_name},
    )

    # 分批寫入
    batch_size = 100
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        col.add(
            ids=[
                hashlib.md5(
                    f"{source_name}_{i + j}_{c['text'][:40]}".encode()
                ).hexdigest()
                for j, c in enumerate(batch)
            ],
            documents=[c["text"] for c in batch],
            metadatas=[
                {
                    "source": c["source"],
                    "chapter": c.get("chapter", ""),
                    "page": c["page"],
                    "article": c.get("article", ""),
                }
                for c in batch
            ],
        )
        if on_progress:
            on_progress(min(i + batch_size, len(all_chunks)), len(all_chunks))

    return {"chunks": len(all_chunks), "already_existed": False}


def get_index_stats() -> list[dict]:
    """回傳所有已建索引的文件資訊。"""
    client = _client()
    ef = _embedding_fn()
    stats = []
    for col_meta in client.list_collections():
        col = client.get_collection(col_meta.name, embedding_function=ef)
        # 從 collection metadata 取得原始檔名
        source = (col_meta.metadata or {}).get("source_name", col_meta.name)
        stats.append({
            "collection_name": col_meta.name,
            "source": source,
            "chunks": col.count(),
        })
    return stats


def remove_doc(collection_name: str) -> None:
    """刪除指定文件的 collection。"""
    _client().delete_collection(collection_name)
