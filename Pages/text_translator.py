"""Halaman 2: Text Translator"""
import base64
import html
import json
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

from App import engine_status, normalize_text, unknown_words

MAX_CHARS = 500
INPUT_HEIGHT = 154
RESULT_KEY = "tt_result"


# =============================================================================
# HELPER TAMPILAN (dipakai juga oleh halaman lain)
# =============================================================================
ICONS = {
    "gamepad": '<line x1="6" x2="10" y1="11" y2="11"/><line x1="8" x2="8" y1="9" y2="13"/><line x1="15" x2="15.01" y1="12" y2="12"/><line x1="18" x2="18.01" y1="10" y2="10"/><path d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258A4 4 0 0 0 17.32 5z"/>',
    "doc": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
    "chat": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "book": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "filesearch": '<path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M4.268 21a2 2 0 0 0 1.727 1H18a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v3"/><path d="m9 18-1.5-1.5"/><circle cx="5" cy="14" r="3"/>',
    "cloud": '<path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2"/><path d="M12 12v9"/><path d="m16 16-4-4-4 4"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
}


def svg(name: str, size: int = 22) -> str:
    path = ICONS.get(name, ICONS["doc"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{path}</svg>'
    )


def page_header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="page-title">{html.escape(title)}</div>'
        f'<div class="page-sub">{html.escape(subtitle)}</div>'
        f'<hr class="page-hr">',
        unsafe_allow_html=True,
    )


def html_table(headers, rows, col_classes=None, truncate=False, empty_text="Belum ada data.", widths=None) -> str:
    col_classes = col_classes or [""] * len(headers)

    colgroup = ""
    if widths:
        cols = "".join(f'<col style="width:{w}">' if w else "<col>" for w in widths)
        colgroup = f"<colgroup>{cols}</colgroup>"

    head = "".join(f'<th class="{c}">{html.escape(h)}</th>' for h, c in zip(headers, col_classes))

    if rows:
        body = "".join(f"<tr>{_table_cells(row, col_classes)}</tr>" for row in rows)
    else:
        body = f'<tr><td colspan="{len(headers)}" class="empty">{html.escape(empty_text)}</td></tr>'

    table_class = "tbl trunc" if truncate else "tbl"
    return (f'<div class="tbl-wrap"><table class="{table_class}">{colgroup}'
            f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')


def _table_cells(row, col_classes) -> str:
    cells = ""
    for value, css_class in zip(row, col_classes):
        text = html.escape(str(value))
        cells += f'<td class="{css_class}" title="{text}">{text}</td>'
    return cells


@st.cache_data(show_spinner=False)
def _read_image_as_data_uri(path: str, modified_time: float) -> str:
    extension = Path(path).suffix.lower().lstrip(".")
    mime = "jpeg" if extension in ("jpg", "jpeg") else extension
    return f"data:image/{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def image_data_uri(path: Path) -> str:
    return _read_image_as_data_uri(str(path), path.stat().st_mtime)


@contextmanager
def loading_overlay(message: str):
    overlay = st.empty()
    overlay.markdown(
        f'<div class="loading-overlay"><div class="loading-box">'
        f'<div class="loading-spinner"></div><div class="loading-text">{html.escape(message)}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    try:
        yield
    finally:
        overlay.empty()


def _page_numbers(page: int, total_pages: int) -> list:
    if total_pages <= 7:
        return list(range(1, total_pages + 1))
    if page <= 4:
        return [1, 2, 3, 4, 5, None, total_pages]
    if page >= total_pages - 3:
        return [1, None] + list(range(total_pages - 4, total_pages + 1))
    return [1, None, page - 1, page, page + 1, None, total_pages]


def _set_page(page_key: str, page: int) -> None:
    st.session_state[page_key] = page


def pager(key: str, page_key: str, page: int, total_pages: int) -> None:
    with st.container(key=key, horizontal=True, horizontal_alignment="center",
                      vertical_alignment="center", gap="small"):
        st.button(":material/chevron_left:", key=f"{key}_prev", disabled=page <= 1,
                  on_click=_set_page, args=(page_key, page - 1))
        for number in _page_numbers(page, total_pages):
            if number is None:
                st.markdown('<div class="pager-gap">…</div>', unsafe_allow_html=True)
            else:
                st.button(str(number), key=f"{key}_{number}", type="primary" if number == page else "secondary",
                          on_click=_set_page, args=(page_key, number))
        st.button(":material/chevron_right:", key=f"{key}_next", disabled=page >= total_pages,
                  on_click=_set_page, args=(page_key, page + 1))


# =============================================================================
# TOMBOL SALIN HASIL
# =============================================================================
ICON_COPY = ('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" '
             'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
             '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>'
             '<path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>'
             '<path d="M16 4h2a2 2 0 0 1 2 2v4"/><path d="M21 14H11"/><path d="m15 10-4 4 4 4"/></svg>')

COPY_COLORS_LIGHT = ("#fff", "#065F46", "#ECFDF5")
COPY_COLORS_DARK = ("transparent", "#6EE7B7", "rgba(16,185,129,.12)")

COPY_BUTTON_TEMPLATE = """
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@600&display=swap" rel="stylesheet">
        <style>
          body{{margin:0;font-family:Inter,sans-serif}}
          button{{display:inline-flex;align-items:center;gap:7px;background:{bg};color:{fg};
                 border:1.5px solid #10B981;border-radius:7px;padding:6px 14px;font-weight:600;
                 font-size:14px;font-family:Inter,sans-serif;cursor:pointer}}
          button:hover{{background:{hover}}}
          svg{{flex-shrink:0}}
        </style>
        <button id="b">{icon}<span id="t">Salin Hasil</span></button>
        <script>
          const t = {payload};
          const b = document.getElementById('b');
          b.onclick = async () => {{
            try {{ await navigator.clipboard.writeText(t); }}
            catch (e) {{
              const a = document.createElement('textarea'); a.value = t;
              document.body.appendChild(a); a.select(); document.execCommand('copy'); a.remove();
            }}
            const t2 = document.getElementById('t');
            t2.textContent = 'Tersalin!';
            setTimeout(() => t2.textContent = 'Salin Hasil', 1800);
          }};
        </script>"""


def _copy_button(text: str) -> None:
    payload = json.dumps(text).replace("</", "<\\/")
    dark = st.session_state.get("dark_mode", False)
    bg, fg, hover = COPY_COLORS_DARK if dark else COPY_COLORS_LIGHT
    button_html = COPY_BUTTON_TEMPLATE.format(bg=bg, fg=fg, hover=hover, icon=ICON_COPY, payload=payload)
    if hasattr(st, "iframe"):
        st.iframe(button_html, height=46)
    else:
        import streamlit.components.v1 as components
        components.html(button_html, height=46)


# =============================================================================
# HALAMAN
# =============================================================================
CHAR_COUNT_SCRIPT = f"""<script>
if (!window.charCountReady) {{
  window.charCountReady = true;
  const update = () => {{
    const box = document.querySelector('textarea[aria-label="Input Teks"]');
    const counter = document.querySelector(".char-count");
    if (!box || !counter) return;
    const label = [...box.value].length + "/{MAX_CHARS} Karakter";
    if (counter.textContent === label) return;
    if (counter.firstChild && counter.firstChild.nodeType === Node.TEXT_NODE) counter.firstChild.nodeValue = label;
    else counter.textContent = label;
  }};
  document.addEventListener("input", update);
  new MutationObserver(update).observe(document.body, {{ childList: true, subtree: true, characterData: true }});
}}
</script>"""


def _text_input() -> str:
    st.markdown('<div class="field-label">Input Teks</div>', unsafe_allow_html=True)
    text = st.text_area("Input Teks", key="tt_input", max_chars=MAX_CHARS, height=INPUT_HEIGHT,
                        label_visibility="collapsed")
    st.markdown(f'<div class="char-count">{len(text)}/{MAX_CHARS} Karakter</div>', unsafe_allow_html=True)
    with st.container(key="char_count_script"):
        try:
            st.html(CHAR_COUNT_SCRIPT, unsafe_allow_javascript=True)
        except TypeError:
            pass
    return text


def _show_engine_note() -> None:
    _, note = engine_status()
    if note:
        st.info(note)


def _show_result(result: str) -> None:
    st.markdown('<div class="field-label" style="margin-top:1.2rem">Hasil Normalisasi</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="result-box">{html.escape(result)}</div><div class="result-line"></div>',
                unsafe_allow_html=True)
    _copy_button(result)


UNKNOWN_TITLE = "Kata belum terdaftar"


def _join_words(words: list[str]) -> str:
    bold = [f"<b>{html.escape(w)}</b>" for w in words]
    if len(bold) <= 2:
        return " dan ".join(bold)
    return ", ".join(bold[:-1]) + ", dan " + bold[-1]


@st.dialog(UNKNOWN_TITLE)
def _unknown_words_dialog(words: list[str]) -> None:
    st.markdown(f'<div class="dlg-icon amber">{svg("alert", 32)}</div>'
                f'<div class="dlg-title">{UNKNOWN_TITLE}</div>'
                f'<div class="dlg-text">Maaf, kata {_join_words(words)} belum terdaftar sehingga hasil '
                f'normalisasi kata tersebut mungkin belum tepat.</div>', unsafe_allow_html=True)
    with st.container(key="dlg_actions", horizontal=True, horizontal_alignment="center"):
        if st.button("Mengerti", type="primary", key="dlg_unknown_ok"):
            st.rerun()


def render() -> None:
    page_header("Text Translator", "Masukkan teks slang game untuk dinormalisasikan ke bahasa Indonesia")
    text = _text_input()
    _show_engine_note()

    if st.button("Normalisasi Teks", type="primary"):
        if text.strip():
            with loading_overlay("Menormalisasi teks..."):
                st.session_state[RESULT_KEY] = normalize_text(text)
            unknown = unknown_words(text)
            if unknown:
                _unknown_words_dialog(unknown)
        else:
            st.session_state[RESULT_KEY] = None
            st.warning("Masukkan teks terlebih dahulu.")

    result = st.session_state.get(RESULT_KEY)
    if result:
        _show_result(result)