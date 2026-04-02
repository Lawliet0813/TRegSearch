"""
core/retriever.py — 跨文件語意查詢，回傳 top-k chunks。

ChromaDB cosine distance → similarity score = 1 - distance
  distance 0.0 → score 1.0（完全相同）
  distance 0.5 → score 0.5（臨界值）
  distance 1.0 → score 0.0（無相關）
"""

from .indexer import _client, _embedding_fn

_SCORE_THRESHOLD = 0.5


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """
    對所有已建索引的 collection 執行語意查詢，合併排序後回傳 top-k。

    Returns:
        [{text, source, chapter, page, article, score}, ...]
        若無任何 collection 則回傳空列表。
    """
    client = _client()
    ef = _embedding_fn()

    collections = client.list_collections()
    if not collections:
        return []

    all_results: list[dict] = []

    for col_meta in collections:
        col = client.get_collection(col_meta.name, embedding_function=ef)
        count = col.count()
        if count == 0:
            continue

        k = min(top_k, count)
        res = col.query(
            query_texts=[query],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )

        for doc, meta, dist in zip(
            res["documents"][0],
            res["metadatas"][0],
            res["distances"][0],
        ):
            score = 1.0 - dist  # cosine distance → similarity
            all_results.append({
                "text": doc,
                "source": meta.get("source", ""),
                "chapter": meta.get("chapter", ""),
                "page": meta.get("page", 0),
                "article": meta.get("article", ""),
                "score": round(score, 4),
            })

    # 跨文件合併排序，取 top-k
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k]


def has_relevant_results(chunks: list[dict]) -> bool:
    """判斷撈出的 chunks 是否有足夠相關度（任一 score >= 閾值）。"""
    return any(c["score"] >= _SCORE_THRESHOLD for c in chunks)
