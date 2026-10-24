"""Halaman 4: Dictionary Slang Game"""
import math

import pandas as pd
import streamlit as st

from App import load_kamus
from Pages.text_translator import html_table, page_header

PAGE_SIZE = 10
SEARCH_DELAY = "200ms"

HEADERS = ["No", "Istilah Slang", "Padanan Baku / Arti Definisi"]
COLUMN_CLASSES = ["num", "slang", ""]
WIDTHS = ["64px", "30%", None]

PAGE_KEY = "dict_page"
LAST_QUERY_KEY = "dict_q"


def _go(delta: int) -> None:
    st.session_state[PAGE_KEY] = st.session_state.get(PAGE_KEY, 1) + delta


def _search_box() -> str:
    options = dict(placeholder="Cari istilah slang gaming...", label_visibility="collapsed",
                   icon=":material/search:", key="dict_search")
    try:
        return st.text_input("Cari", live=SEARCH_DELAY, **options)
    except TypeError:
        return st.text_input("Cari", **options)


def _filter(df: pd.DataFrame, query: str) -> pd.DataFrame:
    query = query.strip()
    if not query:
        return df
    return df[df["slang"].str.contains(query, case=False, regex=False)]


def _current_page(query: str, total_pages: int) -> int:
    if st.session_state.get(LAST_QUERY_KEY) != query:
        st.session_state[LAST_QUERY_KEY] = query
        st.session_state[PAGE_KEY] = 1
    page = min(max(1, st.session_state.get(PAGE_KEY, 1)), total_pages)
    st.session_state[PAGE_KEY] = page
    return page


def _pager(page: int, total_pages: int) -> None:
    with st.container(key="pager", horizontal=True, horizontal_alignment="center",
                      vertical_alignment="center", gap="small"):
        st.button("‹ Sebelumnya", key="prev", disabled=page <= 1, on_click=_go, args=(-1,), type="tertiary")
        st.markdown(f'<div class="page-chip">Halaman {page} dari {total_pages}</div>', unsafe_allow_html=True)
        st.button("Berikutnya ›", key="next", disabled=page >= total_pages, on_click=_go, args=(1,),
                  type="tertiary")


@st.fragment
def _dictionary(df: pd.DataFrame) -> None:
    query = _search_box()
    view = _filter(df, query)

    total_pages = max(1, math.ceil(len(view) / PAGE_SIZE))
    page = _current_page(query, total_pages)

    start = (page - 1) * PAGE_SIZE
    shown = view.iloc[start:start + PAGE_SIZE]
    rows = [[start + i + 1, row.slang, row.baku] for i, row in enumerate(shown.itertuples())]

    with st.container(key="dict_card"):
        st.markdown(html_table(HEADERS, rows, COLUMN_CLASSES, empty_text="Istilah tidak ditemukan.", widths=WIDTHS),
                    unsafe_allow_html=True)
        _pager(page, total_pages)


def render() -> None:
    page_header("Dictionary Slang Game",
                "Kumpulan basis data istilah gaul, jargon, dan singkatan komunitas gamer Indonesia")
    _dictionary(load_kamus())