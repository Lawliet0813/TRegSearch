"""
app.py — TRA RegSearch Streamlit 主程式

UI 依照 regsearch-ui.html 設計稿實作。
啟動：streamlit run app.py
"""

import html
import re
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── 頁面設定（必須最先呼叫）──────────────────────────────────

st.set_page_config(
    page_title="TRA RegSearch · 台鐵運轉規章查詢",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core.indexer import get_index_stats, index_pdf, remove_doc  # noqa: E402
from core.retriever import has_relevant_results, retrieve  # noqa: E402
from core.generator import generate_answer  # noqa: E402

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── CSS ──────────────────────────────────────────────────────

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@300;400;500&family=DM+Mono:wght@300;400;500&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap');

:root {
  --bg:           #f5f2ed;
  --surface:      #faf8f5;
  --surface-2:    #eeebe4;
  --border:       #ddd9d0;
  --border-dark:  #c8c3b8;
  --text:         #1a1814;
  --text-2:       #6b6760;
  --text-3:       #a09c95;
  --accent:       #8b1a1a;
  --accent-light: #f5eeee;
  --rail-dim:     #e8d4d2;
  --green:        #2d6a4f;
  --green-bg:     #edf5f0;
  --chunk-border: #e0dbd2;
  --chunk-bg:     #fdfcfa;
  --tag-bg:       #ede9e2;
}

/* ── 隱藏 Streamlit 預設元素 ── */
#MainMenu, footer, [data-testid="stHeader"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }

/* ── 全域 ── */
.stApp { background: var(--bg) !important; font-family: 'DM Sans', sans-serif; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] > div:first-child { padding: 0 !important; }
[data-testid="stSidebarContent"] { padding: 0 !important; }

/* Sidebar 滾動 */
[data-testid="stSidebarContent"] { overflow-y: auto; }

/* ── Streamlit 元件 reset ── */
.stButton > button {
  font-family: 'DM Sans', sans-serif !important;
  font-size: 13px !important;
}
.stTextArea textarea {
  font-family: 'DM Sans', sans-serif !important;
  font-size: 15px !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  resize: none !important;
  color: var(--text) !important;
}
.stTextArea textarea:focus { box-shadow: none !important; }
[data-baseweb="textarea"] { background: transparent !important; border: none !important; }

/* ── 自訂元件 ── */

/* Topbar */
.tra-topbar {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0 32px;
  display: flex;
  align-items: center;
  height: 52px;
  gap: 0;
  position: sticky;
  top: 0;
  z-index: 100;
}
.tra-logo { display: flex; align-items: center; gap: 10px; }
.tra-logo-mark {
  width: 28px; height: 28px;
  background: var(--accent);
  border-radius: 5px;
  display: flex; align-items: center; justify-content: center;
}
.tra-logo-text {
  font-family: 'Noto Serif TC', serif;
  font-size: 15px; font-weight: 500; color: var(--text);
  letter-spacing: 0.02em;
}
.tra-logo-sub {
  font-size: 10px; color: var(--text-3);
  font-family: 'DM Mono', monospace; letter-spacing: 0.06em;
  margin-top: 1px;
}
.tra-divider {
  width: 1px; height: 20px;
  background: var(--border); margin: 0 20px;
}
.tra-status {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; font-family: 'DM Mono', monospace; color: var(--text-3);
  padding: 4px 10px;
  background: var(--green-bg);
  border: 1px solid #b7d9c8; border-radius: 4px;
  margin-left: auto;
}
.tra-status-dot {
  width: 5px; height: 5px;
  border-radius: 50%; background: var(--green);
}
.tra-status-empty { background: var(--surface-2); border-color: var(--border); }
.tra-status-empty .tra-status-dot { background: var(--text-3); }

/* Sidebar section */
.sb-section {
  padding: 16px 16px 18px;
  border-bottom: 1px solid var(--border);
}
.sb-title {
  font-size: 10px; font-family: 'DM Mono', monospace; color: var(--text-3);
  letter-spacing: 0.1em; text-transform: uppercase;
  margin-bottom: 10px;
}

/* Doc item */
.doc-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: 6px;
  border: 1px solid transparent; margin-bottom: 3px;
  transition: all 0.12s;
}
.doc-item:hover { background: var(--surface-2); }
.doc-icon {
  width: 28px; height: 28px;
  background: var(--accent); border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; padding: 5px;
}
.doc-icon-dim { background: var(--text-3); }
.doc-name {
  font-size: 12.5px; color: var(--text); font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 140px;
}
.doc-meta {
  font-size: 10px; color: var(--text-3);
  font-family: 'DM Mono', monospace; margin-top: 1px;
}

/* Setting row */
.setting-row {
  display: flex; align-items: center;
  justify-content: space-between; margin-bottom: 10px;
}
.setting-label { font-size: 12px; color: var(--text-2); }
.setting-val {
  font-size: 11px; font-family: 'DM Mono', monospace; color: var(--text-3);
  background: var(--surface-2); padding: 2px 8px;
  border-radius: 3px; border: 1px solid var(--border);
}

/* Search box */
.search-wrap {
  padding: 24px 32px 0;
}
.search-box {
  display: flex; align-items: flex-start; gap: 10px;
  background: var(--surface);
  border: 1.5px solid var(--border-dark);
  border-radius: 10px;
  padding: 8px 14px;
  transition: border-color 0.15s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.search-box:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(139,26,26,0.08);
}
.search-icon { color: var(--text-3); margin-top: 6px; flex-shrink: 0; }
.search-hint {
  font-size: 11px; color: var(--text-3);
  font-family: 'DM Mono', monospace; margin-top: 6px;
  padding: 0 2px;
}

/* Example query buttons */
.example-q-row { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; padding: 0 2px; }
.example-q-btn {
  padding: 3px 9px; border-radius: 3px;
  border: 1px solid var(--border);
  background: var(--surface);
  font-size: 11px; color: var(--text-2);
  cursor: pointer; transition: all 0.12s;
  font-family: 'DM Sans', sans-serif;
}
.example-q-btn:hover {
  border-color: var(--accent); color: var(--accent);
  background: var(--accent-light);
}

/* Results area */
.results-wrap { padding: 20px 32px 32px; }
.chunks-header {
  display: flex; align-items: center;
  justify-content: space-between; margin-bottom: 12px;
}
.chunks-title {
  font-size: 11px; font-family: 'DM Mono', monospace;
  color: var(--text-3); letter-spacing: 0.08em; text-transform: uppercase;
}
.chunks-count { font-size: 11px; font-family: 'DM Mono', monospace; color: var(--text-3); }

/* Answer card */
.answer-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px; margin-bottom: 20px;
  overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.answer-header {
  padding: 10px 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px;
  background: var(--accent-light);
}
.answer-label {
  font-size: 11px; font-family: 'DM Mono', monospace;
  color: var(--accent); letter-spacing: 0.06em; text-transform: uppercase;
}
.answer-model {
  margin-left: auto; font-size: 10px;
  font-family: 'DM Mono', monospace; color: var(--text-3);
  padding: 2px 7px; background: white;
  border: 1px solid var(--border); border-radius: 3px;
}
.answer-body {
  padding: 16px; line-height: 1.8;
  color: var(--text); font-size: 14px;
}
.answer-body p { margin-bottom: 10px; }
.answer-body p:last-child { margin-bottom: 0; }
.answer-body strong { color: var(--accent); font-weight: 500; }
.cite-ref {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px;
  background: var(--accent); color: white;
  border-radius: 3px; font-size: 9px;
  font-family: 'DM Mono', monospace; font-weight: 500;
  margin: 0 2px; vertical-align: middle;
}

/* Chunk card */
.chunk-card {
  background: var(--chunk-bg);
  border: 1px solid var(--chunk-border);
  border-radius: 8px; margin-bottom: 10px; overflow: hidden;
  transition: border-color 0.12s;
}
.chunk-card:hover { border-color: var(--border-dark); }
.chunk-card.highlighted {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(139,26,26,0.08);
}
.chunk-header {
  padding: 8px 12px; border-bottom: 1px solid var(--chunk-border);
  display: flex; align-items: center; gap: 8px;
  background: var(--surface-2);
}
.chunk-num {
  width: 18px; height: 18px;
  background: var(--accent); color: white;
  border-radius: 3px; font-size: 10px;
  font-family: 'DM Mono', monospace;
  display: flex; align-items: center; justify-content: center;
  font-weight: 500; flex-shrink: 0;
}
.chunk-source { font-size: 11px; font-family: 'DM Mono', monospace; color: var(--text-2); }
.chunk-score {
  margin-left: auto; font-size: 10px;
  font-family: 'DM Mono', monospace; color: var(--text-3);
  display: flex; align-items: center; gap: 4px;
}
.score-bar {
  width: 40px; height: 3px;
  background: var(--border); border-radius: 2px; overflow: hidden;
}
.score-fill { height: 100%; background: var(--green); border-radius: 2px; }
.chunk-body {
  padding: 12px; font-size: 13.5px;
  line-height: 1.75; color: var(--text-2);
}
.chunk-body mark {
  background: #fef3c7; color: var(--text);
  padding: 0 2px; border-radius: 2px;
}
.chunk-tags {
  padding: 8px 12px; display: flex; gap: 5px; flex-wrap: wrap;
  border-top: 1px solid var(--chunk-border);
}
.tag {
  padding: 2px 7px; background: var(--tag-bg);
  border: 1px solid var(--border); border-radius: 3px;
  font-size: 10px; font-family: 'DM Mono', monospace; color: var(--text-3);
}
.tag-chapter {
  color: var(--accent); background: var(--accent-light);
  border-color: var(--rail-dim);
}

/* Empty state */
.empty-state {
  text-align: center; padding: 60px 20px; color: var(--text-3);
}
.empty-title {
  font-family: 'Noto Serif TC', serif; font-size: 18px;
  color: var(--text-2); margin-bottom: 8px;
}
.empty-sub { font-size: 13px; line-height: 1.6; }

/* Stримlit 覆蓋：讓 sidebar widget 更乾淨 */
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stSlider label,
section[data-testid="stSidebar"] .stRadio label {
  font-size: 12px !important; color: var(--text-2) !important;
}
section[data-testid="stSidebar"] .stRadio > div {
  flex-direction: row !important; gap: 6px !important;
}
section[data-testid="stSidebar"] .stButton > button {
  width: 100% !important;
  background: var(--accent) !important;
  color: white !important;
  border: none !important;
  border-radius: 6px !important;
  padding: 7px 0 !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  background: #7a1616 !important;
}
/* Delete button */
.del-btn > button {
  background: transparent !important;
  color: var(--text-3) !important;
  border: 1px solid var(--border) !important;
  border-radius: 4px !important;
  padding: 2px 6px !important;
  font-size: 11px !important;
  min-height: unset !important;
  height: 22px !important;
}
.del-btn > button:hover {
  color: var(--accent) !important;
  border-color: var(--accent) !important;
}
/* Search submit button */
.search-submit > button {
  background: var(--accent) !important;
  color: white !important;
  border: none !important;
  border-radius: 6px !important;
  padding: 7px 16px !important;
  white-space: nowrap !important;
}
.search-submit > button:hover { background: #7a1616 !important; }
</style>
"""

st.markdown(_CSS, unsafe_allow_html=True)


# ── 狀態初始化 ────────────────────────────────────────────────

def _init():
    defaults = {
        "query_val": "",
        "auto_search": False,
        "chunks": [],
        "answer": "",
        "llm_mode": "offline",
        "top_k": 5,
        "chunk_size": 512,
        "searched": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()


# ── 輔助函式 ──────────────────────────────────────────────────

_PDF_ICON = """<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
  <path d="M3 1h6l3 3v9H3V1z" stroke="white" stroke-width="1.2" stroke-linejoin="round"/>
  <path d="M9 1v3h3" stroke="white" stroke-width="1.2"/>
</svg>"""

_STAR_ICON = """<svg width="13" height="13" viewBox="0 0 13 13" fill="none">
  <path d="M6.5 1L8 5h4l-3.2 2.3 1.2 4L6.5 9 3.5 11.3l1.2-4L1.5 5h4L6.5 1z" fill="#8b1a1a"/>
</svg>"""


def _highlight(text: str, query: str) -> str:
    """在 chunk 文字中高亮 query 關鍵詞。"""
    if not query:
        return html.escape(text)
    escaped = html.escape(text)
    words = [w for w in query.split() if len(w) >= 2]
    if not words:
        # 整個 query 視為一個詞
        words = [query]
    for word in words:
        pattern = re.compile(re.escape(html.escape(word)), re.IGNORECASE)
        escaped = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped)
    return escaped


def _answer_to_html(text: str) -> str:
    """LLM 回答文字 → HTML（保留段落、粗體、引用標號）。"""
    escaped = html.escape(text)
    # **粗體**
    escaped = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", escaped)
    # [N] 引用編號 → 小方塊
    escaped = re.sub(r"\[(\d+)\]", r'<span class="cite-ref">\1</span>', escaped)
    # 段落
    paras = re.split(r"\n\n+", escaped)
    inner = "".join(
        f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paras if p.strip()
    )
    return inner or f"<p>{escaped}</p>"


def _model_label(mode: str) -> str:
    if mode == "api":
        return "claude-sonnet-4 · API"
    return "mlx-community/Llama-3.2-3B · 離線"


# ── Topbar ────────────────────────────────────────────────────

def _render_topbar(stats: list[dict]) -> None:
    total_chunks = sum(d["chunks"] for d in stats)
    n_docs = len(stats)
    if stats:
        status_cls = ""
        status_txt = f"索引就緒 · {n_docs} 份文件 · {total_chunks:,} 段"
    else:
        status_cls = "tra-status-empty"
        status_txt = "尚無文件 · 請上傳 PDF"

    st.markdown(
        f"""
        <div class="tra-topbar">
          <div class="tra-logo">
            <div class="tra-logo-mark">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 8h12M8 2v12" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
                <circle cx="8" cy="8" r="3" stroke="white" stroke-width="1.5"/>
              </svg>
            </div>
            <div>
              <div class="tra-logo-text">RegSearch</div>
              <div class="tra-logo-sub">台鐵運轉規章查詢系統</div>
            </div>
          </div>
          <div class="tra-divider"></div>
          <div class="tra-status {status_cls}">
            <div class="tra-status-dot"></div>
            {status_txt}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Sidebar ───────────────────────────────────────────────────

def _render_sidebar(stats: list[dict]) -> None:
    # ── 上傳區 ──
    st.markdown('<div class="sb-section"><div class="sb-title">上傳文件</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "上傳 PDF",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if uploaded:
        for f in uploaded:
            dest = UPLOAD_DIR / f.name
            dest.write_bytes(f.read())
            with st.spinner(f"建索引：{f.name}"):
                result = index_pdf(str(dest), f.name, chunk_size=st.session_state.chunk_size)
            if result["already_existed"]:
                st.info(f"「{f.name}」已建索引，跳過。")
            else:
                st.success(f"完成！共 {result['chunks']} 段。")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # ── 文件清單 ──
    st.markdown('<div class="sb-section"><div class="sb-title">已載入文件</div>', unsafe_allow_html=True)
    if not stats:
        st.markdown(
            '<p style="font-size:12px;color:var(--text-3);margin:0">尚未上傳任何文件</p>',
            unsafe_allow_html=True,
        )
    else:
        for i, doc in enumerate(stats):
            col_a, col_b = st.columns([8, 2])
            with col_a:
                icon_cls = "" if i == 0 else "doc-icon-dim"
                st.markdown(
                    f"""
                    <div class="doc-item">
                      <div class="doc-icon {icon_cls}">{_PDF_ICON}</div>
                      <div>
                        <div class="doc-name">{html.escape(doc['source'])}</div>
                        <div class="doc-meta">{doc['chunks']} 段 · 已建索引</div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col_b:
                st.markdown('<div class="del-btn">', unsafe_allow_html=True)
                if st.button("✕", key=f"del_{doc['collection_name']}"):
                    remove_doc(doc["collection_name"])
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── 模型設定 ──
    st.markdown('<div class="sb-section"><div class="sb-title">模型設定</div>', unsafe_allow_html=True)

    mode = st.radio(
        "LLM 模式",
        options=["offline", "api"],
        format_func=lambda x: "離線" if x == "offline" else "API",
        horizontal=True,
        key="llm_mode",
        label_visibility="collapsed",
    )
    st.markdown(
        f'<div class="setting-row"><span class="setting-label">LLM</span>'
        f'<span class="setting-val">{"離線 (MLX)" if mode == "offline" else "Claude API"}</span></div>',
        unsafe_allow_html=True,
    )

    top_k = st.select_slider(
        "撈取段數",
        options=[3, 5, 8],
        value=st.session_state.top_k,
        key="top_k",
    )
    st.markdown(
        f'<div class="setting-row"><span class="setting-label">撈取段數</span>'
        f'<span class="setting-val">top {top_k}</span></div>',
        unsafe_allow_html=True,
    )

    chunk_size = st.select_slider(
        "Chunk 大小",
        options=[256, 512, 1024],
        value=st.session_state.chunk_size,
        key="chunk_size",
    )
    st.markdown(
        f'<div class="setting-row" style="margin-bottom:0">'
        f'<span class="setting-label">Chunk 大小</span>'
        f'<span class="setting-val">{chunk_size} chars</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="setting-row" style="margin-bottom:0">'
        '<span class="setting-label">Embedding</span>'
        '<span class="setting-val" style="font-size:9px">paraphrase-multilingual</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


# ── 查詢區 ────────────────────────────────────────────────────

_EXAMPLE_QUERIES = ["過站不停定義", "停車位置不當處置", "緊急制動條件", "進站速度限制"]


def _render_search(has_docs: bool) -> str | None:
    """渲染搜尋框，回傳觸發的查詢字串（None 表示未觸發）。"""
    st.markdown('<div class="search-wrap">', unsafe_allow_html=True)

    # 搜尋框外框
    st.markdown(
        '<div class="search-box">'
        '<div class="search-icon"><svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
        '<circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5"/>'
        '<path d="M11 11l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
        "</svg></div>",
        unsafe_allow_html=True,
    )

    query_col, btn_col = st.columns([10, 1])
    with query_col:
        query = st.text_area(
            "query",
            value=st.session_state.query_val,
            placeholder="輸入查詢，例如：ATP 系統異常時機車長的處置程序為何？",
            height=56,
            label_visibility="collapsed",
            key="_query_input",
        )
    with btn_col:
        st.markdown('<div class="search-submit">', unsafe_allow_html=True)
        search_clicked = st.button(
            "查詢",
            disabled=not has_docs,
            use_container_width=False,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)  # .search-box

    # 提示 + 快捷按鈕
    st.markdown('<div class="search-hint">↵ 查詢 · 支援自然語言</div>', unsafe_allow_html=True)
    st.markdown('<div class="example-q-row">', unsafe_allow_html=True)
    ex_cols = st.columns(len(_EXAMPLE_QUERIES))
    auto_query = None
    for i, eq in enumerate(_EXAMPLE_QUERIES):
        with ex_cols[i]:
            if st.button(eq, key=f"eq_{i}", use_container_width=True):
                st.session_state.query_val = eq
                st.session_state.auto_search = True
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)  # .example-q-row
    st.markdown("</div>", unsafe_allow_html=True)  # .search-wrap

    # 決定是否觸發查詢
    if search_clicked and query.strip():
        st.session_state.query_val = query.strip()
        return query.strip()
    if st.session_state.auto_search:
        st.session_state.auto_search = False
        return st.session_state.query_val
    return None


# ── 結果區 ────────────────────────────────────────────────────

def _render_chunk_card(chunk: dict, idx: int, query: str, is_top: bool) -> None:
    highlighted_cls = "highlighted" if is_top else ""
    score = chunk.get("score", 0.0)
    score_pct = max(0, min(100, int(score * 100)))

    source = html.escape(chunk.get("source", ""))
    chapter = html.escape(chunk.get("chapter", ""))
    page = chunk.get("page", "")
    article = html.escape(chunk.get("article", ""))

    source_label = source
    if chapter:
        source_label += f" · {chapter}"
    if page:
        source_label += f" · p.{page}"

    body_html = _highlight(chunk.get("text", ""), query)

    # tags
    tags_html = ""
    if chapter:
        tags_html += f'<span class="tag tag-chapter">{html.escape(chapter)}</span>'
    if article:
        tags_html += f'<span class="tag">{html.escape(article)}</span>'
    if not tags_html:
        tags_html = '<span class="tag">條文</span>'

    st.markdown(
        f"""
        <div class="chunk-card {highlighted_cls}">
          <div class="chunk-header">
            <div class="chunk-num">{idx}</div>
            <span class="chunk-source">{source_label}</span>
            <div class="chunk-score">
              <div class="score-bar"><div class="score-fill" style="width:{score_pct}%"></div></div>
              {score:.2f}
            </div>
          </div>
          <div class="chunk-body">{body_html}</div>
          <div class="chunk-tags">{tags_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _do_search(query: str) -> None:
    """執行查詢，結果存入 session state。"""
    with st.spinner("正在搜尋相關條文…"):
        chunks = retrieve(query, top_k=st.session_state.top_k)
    st.session_state.chunks = chunks
    st.session_state.searched = True

    if not chunks or not has_relevant_results(chunks):
        st.session_state.answer = "找不到足夠相關的條文，建議換個關鍵字查詢。"
        return

    # 生成回答
    answer_placeholder = st.empty()
    with answer_placeholder:
        with st.spinner("正在生成回答（離線模型首次載入約需 10–30 秒）…"
                        if st.session_state.llm_mode == "offline"
                        else "正在呼叫 Claude API…"):
            full_answer = "".join(
                generate_answer(query, chunks, mode=st.session_state.llm_mode)
            )
    answer_placeholder.empty()
    st.session_state.answer = full_answer


def _render_results(query: str) -> None:
    st.markdown('<div class="results-wrap">', unsafe_allow_html=True)

    chunks = st.session_state.chunks
    answer = st.session_state.answer

    if not st.session_state.searched:
        # 空狀態
        st.markdown(
            """
            <div class="empty-state">
              <div class="empty-title">輸入查詢以搜尋規章條文</div>
              <div class="empty-sub">
                支援自然語言查詢，例如：「ATP 系統異常時機車長的處置程序」<br>
                請先在左側欄上傳 PDF 規章文件
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif not chunks or not has_relevant_results(chunks):
        # 無結果
        st.markdown(
            """
            <div class="empty-state">
              <div class="empty-title">找不到相關條文</div>
              <div class="empty-sub">
                相似度過低，建議換個關鍵字查詢。<br>
                可嘗試使用更具體的術語，例如：「ATP 降級模式」、「進站速度限制」。
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # AI 整合回答
        model_lbl = _model_label(st.session_state.llm_mode)
        answer_html = _answer_to_html(answer)
        st.markdown(
            f"""
            <div class="answer-card">
              <div class="answer-header">
                {_STAR_ICON}
                <span class="answer-label">整合回答</span>
                <span class="answer-model">{html.escape(model_lbl)}</span>
              </div>
              <div class="answer-body">{answer_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 來源條文
        relevant = [c for c in chunks if c["score"] >= 0.5]
        st.markdown(
            f"""
            <div class="chunks-header">
              <span class="chunks-title">參考條文來源</span>
              <span class="chunks-count">{len(relevant)} 段 · 相似度排序</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        for i, chunk in enumerate(relevant, 1):
            _render_chunk_card(chunk, i, query, is_top=(i == 1))

    st.markdown("</div>", unsafe_allow_html=True)  # .results-wrap


# ── 主程式 ────────────────────────────────────────────────────

def main() -> None:
    stats = get_index_stats()

    # Sidebar
    with st.sidebar:
        _render_sidebar(stats)

    # 重新取得最新 stats（sidebar 可能剛完成 indexing）
    stats = get_index_stats()
    has_docs = len(stats) > 0

    # Topbar
    _render_topbar(stats)

    # Search
    triggered_query = _render_search(has_docs)
    if triggered_query:
        _do_search(triggered_query)
        st.rerun()

    # Results
    _render_results(st.session_state.query_val)


if __name__ == "__main__":
    main()
