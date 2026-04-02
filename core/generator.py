"""
core/generator.py — LLM 整合回答。

支援兩種模式：
  offline — MLX 本機推論（mlx-community/Llama-3.2-3B-Instruct-4bit）
  api     — Anthropic Claude API（claude-sonnet-4-20250514）

核心安全限制：LLM 只能依據撈到的 chunks 回答，
system prompt 明確禁止引用訓練資料中的規章知識。
"""

import os
from typing import Generator

from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = (
    "你是台鐵運轉規章查詢助理。"
    "請嚴格依據以下提供的條文內容回答使用者問題，"
    "不得自行補充條文以外的規章資訊，也不得引用訓練資料中的規章知識。\n\n"
    "回答格式：\n"
    "- 使用繁體中文（台灣慣用語）\n"
    "- 條列式說明，邏輯清晰\n"
    "- 引用條文時標示來源編號，例如「依據 [1]……」\n"
    "- 若提供的條文不足以完整回答，請明確說明\n\n"
    "僅依據提供的條文作答，不得添加條文外的內容。"
)


def _format_context(chunks: list[dict]) -> str:
    """將 chunks 格式化為 prompt 的參考條文區塊。"""
    parts = []
    for i, c in enumerate(chunks, 1):
        source = c.get("source", "")
        chapter = c.get("chapter", "")
        page = c.get("page", "")
        article = c.get("article", "")

        label = source
        if chapter:
            label += f" · {chapter}"
        if page:
            label += f" · 第 {page} 頁"
        if article:
            label += f" · {article}"

        parts.append(f"[{i}] 來源：{label}\n{c['text']}")
    return "\n\n---\n\n".join(parts)


# ── 離線模式（MLX）────────────────────────────────────────────


def _generate_offline(query: str, chunks: list[dict]) -> Generator[str, None, None]:
    try:
        from mlx_lm import load, generate  # type: ignore
    except ImportError:
        yield (
            "❌ 離線模式需要安裝 mlx-lm（僅支援 Apple Silicon Mac）。\n"
            "請執行 `pip install mlx-lm` 後重試，或切換至 API 模式。"
        )
        return

    context = _format_context(chunks)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"參考條文：\n\n{context}\n\n問題：{query}",
        },
    ]

    try:
        model, tokenizer = load("mlx-community/Llama-3.2-3B-Instruct-4bit")

        if (
            hasattr(tokenizer, "apply_chat_template")
            and tokenizer.chat_template is not None
        ):
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            prompt = (
                f"{_SYSTEM_PROMPT}\n\n"
                f"參考條文：\n{context}\n\n"
                f"問題：{query}\n\n回答："
            )

        response = generate(model, tokenizer, prompt=prompt, max_tokens=1024, verbose=False)
        yield response

    except Exception as exc:
        yield f"❌ 離線模型錯誤：{exc}"


# ── API 模式（Anthropic）──────────────────────────────────────


def _generate_api(query: str, chunks: list[dict]) -> Generator[str, None, None]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        yield (
            "❌ 未設定 ANTHROPIC_API_KEY。\n"
            "請在專案根目錄建立 `.env` 檔並填入金鑰後重啟，\n"
            "或參考 `.env.example`。"
        )
        return

    try:
        import anthropic  # type: ignore
    except ImportError:
        yield "❌ API 模式需要安裝 anthropic 套件：`pip install anthropic`"
        return

    context = _format_context(chunks)
    user_msg = f"參考條文：\n\n{context}\n\n問題：{query}"

    client = anthropic.Anthropic(api_key=api_key)
    try:
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as exc:
        yield f"❌ API 錯誤：{exc}"


# ── 主要 API ──────────────────────────────────────────────────


def generate_answer(
    query: str, chunks: list[dict], mode: str = "offline"
) -> Generator[str, None, None]:
    """
    依 mode 選擇 LLM 產生回答。

    Args:
        query:  使用者的自然語言問題
        chunks: retriever 撈出的條文列表（含 score）
        mode:   "offline" | "api"

    Yields:
        str — 回答文字片段（streaming）
    """
    if not chunks:
        yield "找不到相關條文，建議換個關鍵字查詢。"
        return

    # 全部 chunks 相似度均低於閾值
    if all(c.get("score", 1.0) < 0.5 for c in chunks):
        yield "找不到足夠相關的條文（相似度過低），建議換個關鍵字查詢。"
        return

    if mode == "api":
        yield from _generate_api(query, chunks)
    else:
        yield from _generate_offline(query, chunks)
