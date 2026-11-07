"""Halaman 5: Panel Admin"""
import hmac
import html
import json
import math
import re
import time
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from App import (BASE_DIR, DATA_REPO, MAX_PHRASE_WORDS, active_model, clean_key, get_secret, kamus_bytes,
                 load_data_baru, load_kamus, load_mt5, refresh_store, reload_model, remote_storage, save_data_baru,
                 save_kamus, set_active_model, store_error)
from Pages.text_translator import html_table, page_header, pager, svg

ADMIN_KEY = "is_admin"
GO_ADMIN_KEY = "adm_go"
PAGES_KEY = "PAGES"
FLASH_KEY = "adm_flash"
ADD_FORM_KEY = "adm_add_form"
MODEL_FORM_KEY = "adm_model_form"
LIST_PAGE_KEY = "adm_list_page"
LIST_QUERY_KEY = "adm_list_q"
DATA_PAGE_KEY = "adm_data_page"

PAGE_SIZE = 10
SEARCH_DELAY = "200ms"
MAX_EXAMPLES = 10
MAX_SENTENCE_CHARS = 500
NEW_DAYS = 14
TIMEZONE = ZoneInfo("Asia/Jakarta")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

NOTEBOOK_NAME = "Fine_tuning_Lanjutan_ModelMT5.ipynb"
NOTEBOOK_PATH = BASE_DIR / NOTEBOOK_NAME
NOTEBOOK_MODEL_RE = re.compile(r'^((?:OLD|NEW)_MODEL_ID) = "[^"]*"', flags=re.M)
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

DATA_HEADERS = ["No", "Kalimat Slang", "Kalimat Baku", "Istilah", "Ditambahkan"]
DATA_CLASSES = ["num", "bold", "", "slang", ""]
DATA_WIDTHS = ["58px", "32%", None, "14%", "136px"]


# =============================================================================
# LOGIN
# =============================================================================
def _credentials() -> tuple[str | None, str | None]:
    return get_secret("ADMIN_USERNAME"), get_secret("ADMIN_PASSWORD")


def is_admin() -> bool:
    return st.session_state.get(ADMIN_KEY, False)


def _check_login(username: str, password: str) -> bool:
    expected_username, expected_password = _credentials()
    if not (expected_username and expected_password):
        return False
    username_ok = hmac.compare_digest(username.strip().encode(), str(expected_username).encode())
    password_ok = hmac.compare_digest(password.encode(), str(expected_password).encode())
    return username_ok and password_ok


def _dialog_heading(icon: str, tone: str, title: str, message: str) -> None:
    st.markdown(f'<div class="dlg-icon {tone}">{svg(icon, 32)}</div>'
                f'<div class="dlg-title">{html.escape(title)}</div>'
                f'<div class="dlg-text">{message}</div>', unsafe_allow_html=True)


def _field_error(slot, message: str) -> None:
    slot.markdown(f'<div class="adm-error">{svg("alert", 15)}{html.escape(message)}</div>', unsafe_allow_html=True)


LOGIN_TITLE = "Masuk sebagai Admin"


@st.dialog(LOGIN_TITLE)
def login_dialog() -> None:
    _dialog_heading("lock", "blue", LOGIN_TITLE,
                    "Halaman admin dipakai untuk memperbarui kamus slang game, data latih, dan model.")
    if not all(_credentials()):
        st.markdown('<div class="dlg-text">Akun admin belum diatur. Isi <b>ADMIN_USERNAME</b> dan '
                    '<b>ADMIN_PASSWORD</b> di Secrets aplikasi.</div>', unsafe_allow_html=True)
        with st.container(key="dlg_actions", horizontal=True, horizontal_alignment="center"):
            if st.button("Mengerti", type="primary", key="dlg_login_ok"):
                st.rerun()
        return

    with st.form("login_form", border=False, enter_to_submit=True):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        error = st.empty()
        with st.container(key="dlg_actions_rev", horizontal=True, horizontal_alignment="center"):
            submitted = st.form_submit_button("Masuk", type="primary")
            cancelled = st.form_submit_button("Batal")
    if cancelled:
        st.rerun()
    if submitted:
        if _check_login(username, password):
            st.session_state[ADMIN_KEY] = True
            st.session_state[GO_ADMIN_KEY] = True
            st.rerun()
        time.sleep(1)
        _field_error(error, "Username atau password salah.")


def _go_to_admin_after_login() -> None:
    if st.session_state.pop(GO_ADMIN_KEY, False):
        st.switch_page(st.session_state[PAGES_KEY]["admin"])


def admin_button() -> None:
    _go_to_admin_after_login()
    if is_admin():
        if st.button("Panel Admin", icon=":material/admin_panel_settings:", key="adm_open"):
            st.switch_page(st.session_state[PAGES_KEY]["admin"])
    elif st.button("Masuk sebagai Admin", icon=":material/lock:", key="adm_login"):
        login_dialog()


@contextmanager
def header_with_actions(title: str, subtitle: str, key: str):
    with st.container(key=key, horizontal=True, vertical_alignment="bottom", gap="small"):
        st.markdown(f'<div class="page-title">{html.escape(title)}</div>'
                    f'<div class="page-sub">{html.escape(subtitle)}</div>', unsafe_allow_html=True, width="stretch")
        yield
    st.markdown('<hr class="page-hr">', unsafe_allow_html=True)


# =============================================================================
# TANGGAL & PESAN
# =============================================================================
def today() -> date:
    return datetime.now(TIMEZONE).date()


def _parse_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def format_date(value, empty: str = "kamus awal") -> str:
    day = _parse_date(value)
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}" if day else empty


def is_new(value) -> bool:
    day = _parse_date(value)
    return day is not None and (today() - day).days <= NEW_DAYS


def _flash(message: str, warnings=()) -> None:
    st.session_state[FLASH_KEY] = (message, [w for w in warnings if w])


def _show_flash() -> None:
    item = st.session_state.pop(FLASH_KEY, None)
    if item:
        message, warnings = item
        st.toast(message, icon=":material/check_circle:")
        for warning in warnings:
            st.warning(warning)


def _section_heading(title: str, subtitle: str = "") -> None:
    sub = f'<div class="adm-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(f'<div class="adm-title">{html.escape(title)}</div>{sub}', unsafe_allow_html=True, width="stretch")


# =============================================================================
# VALIDASI KAMUS
# =============================================================================
def _normalize(text) -> str:
    return " ".join(str(text or "").split())


def _term_problem(slang: str, others: pd.DataFrame) -> str | None:
    key = clean_key(slang)
    if not key:
        return "Istilah slang wajib diisi."
    if len(key.split()) > MAX_PHRASE_WORDS:
        return f"Istilah slang maksimal {MAX_PHRASE_WORDS} kata."
    if key in {clean_key(s) for s in others["slang"]}:
        return f'Istilah "{slang}" sudah ada di kamus.'
    return None


def _example_problem(slang: str, pairs: list[tuple[str, str]]) -> tuple[str | None, list[tuple[str, str]]]:
    key = f" {clean_key(slang)} "
    complete = []
    for number, (source, target) in enumerate(pairs, start=1):
        if not source and not target:
            continue
        if not source or not target:
            return f"Contoh kalimat nomor {number} belum lengkap.", []
        if key not in f" {clean_key(source)} ":
            return f'Kalimat slang nomor {number} belum memuat istilah "{slang}".', []
        complete.append((source, target))
    if not complete:
        return "Tambahkan minimal 1 contoh kalimat.", []
    return None, list(dict.fromkeys(complete))


def _insert_term(kamus: pd.DataFrame, slang: str, baku: str) -> pd.DataFrame:
    row = pd.DataFrame([{"slang": slang, "baku": baku, "ditambahkan": today().isoformat()}])
    return pd.concat([kamus, row], ignore_index=True).sort_values("slang", kind="stable", ignore_index=True)


# =============================================================================
# TAB 1: KELOLA KAMUS
# =============================================================================
def _add_example(form_id: int) -> None:
    rows = st.session_state[f"{ADD_FORM_KEY}_{form_id}"]
    rows.append(max(rows, default=-1) + 1)


def _remove_example(form_id: int, row_id: int) -> None:
    st.session_state[f"{ADD_FORM_KEY}_{form_id}"].remove(row_id)


def _reset_add_form() -> None:
    st.session_state[ADD_FORM_KEY] = st.session_state.get(ADD_FORM_KEY, 0) + 1


def _example_rows(form_id: int) -> list[tuple[str, str]]:
    rows = st.session_state.setdefault(f"{ADD_FORM_KEY}_{form_id}", [0, 1, 2])
    st.markdown('<div class="field-label">Contoh kalimat</div>'
                '<div class="ex-head"><span>No</span><span>Kalimat slang</span><span>Kalimat baku</span></div>',
                unsafe_allow_html=True)
    pairs = []
    for number, row_id in enumerate(rows, start=1):
        with st.container(key=f"ex_row_{form_id}_{row_id}", horizontal=True, vertical_alignment="center",
                          gap="small"):
            st.markdown(f'<div class="row-num">{number}</div>', unsafe_allow_html=True, width=36)
            source = st.text_input(f"Kalimat slang {number}", key=f"ex_src_{form_id}_{row_id}",
                                   max_chars=MAX_SENTENCE_CHARS, placeholder="Kalimat slang",
                                   label_visibility="collapsed")
            target = st.text_input(f"Kalimat baku {number}", key=f"ex_tgt_{form_id}_{row_id}",
                                   max_chars=MAX_SENTENCE_CHARS, placeholder="Kalimat baku",
                                   label_visibility="collapsed")
            st.button("", icon=":material/delete:", key=f"ex_del_{form_id}_{row_id}",
                      on_click=_remove_example, args=(form_id, row_id), disabled=len(rows) == 1)
        pairs.append((_normalize(source), _normalize(target)))

    with st.container(key="ex_more", horizontal=True, vertical_alignment="center", gap="small"):
        st.button("Tambah contoh kalimat", icon=":material/add:", key=f"ex_add_{form_id}",
                  on_click=_add_example, args=(form_id,), disabled=len(rows) >= MAX_EXAMPLES)
        st.markdown('<div class="adm-note">Minimal 1, disarankan 3–5. Setiap kalimat slang harus memuat '
                    'istilah yang ditambahkan.</div>', unsafe_allow_html=True, width="stretch")
    return pairs


DUPLICATE_TITLE = "Istilah sudah terdaftar"


def _registered_term(slang: str, kamus: pd.DataFrame):
    key = clean_key(slang)
    matches = kamus[kamus["slang"].map(clean_key) == key]
    return matches.iloc[0] if key and not matches.empty else None


@st.dialog(DUPLICATE_TITLE)
def _duplicate_dialog(slang: str, baku: str) -> None:
    _dialog_heading("alert", "amber", DUPLICATE_TITLE,
                    f"Istilah <b>{html.escape(slang)}</b> sudah terdaftar di kamus dengan padanan baku "
                    f"<b>{html.escape(baku)}</b>. Untuk mengubahnya, gunakan ikon pensil di Daftar Kamus.")
    with st.container(key="dlg_actions", horizontal=True, horizontal_alignment="center"):
        if st.button("Mengerti", type="primary", key="dlg_duplicate_ok"):
            st.rerun()


def _save_new_term(slang: str, baku: str, pairs: list[tuple[str, str]], error) -> None:
    kamus = load_kamus()
    slang = _normalize(slang).lower()
    baku = _normalize(baku)
    registered = _registered_term(slang, kamus)
    if registered is not None:
        _duplicate_dialog(registered["slang"], registered["baku"])
        return
    problem = _term_problem(slang, kamus) or (None if baku else "Padanan baku wajib diisi.")
    if not problem:
        problem, pairs = _example_problem(slang, pairs)
    if problem:
        _field_error(error, problem)
        return

    data = load_data_baru()
    known = set(data["clean_comment"].str.lower())
    added = today().isoformat()
    new_rows = pd.DataFrame([{"clean_comment": s, "baku_reference": t, "istilah": slang, "ditambahkan": added}
                             for s, t in pairs if s.lower() not in known])
    warnings = [save_kamus(_insert_term(kamus, slang, baku))]
    if not new_rows.empty:
        warnings.append(save_data_baru(pd.concat([data, new_rows], ignore_index=True)))
    _reset_add_form()
    _flash(f'Istilah "{slang}" dan {len(new_rows)} contoh kalimat tersimpan.', warnings)
    st.rerun()


@st.fragment
def _add_form(disabled: bool) -> None:
    form_id = st.session_state.get(ADD_FORM_KEY, 0)
    with st.container(key="adm_add"):
        _section_heading("Tambah Slang Baru", "Istilah langsung dipakai lexical mapping. Contoh kalimat disimpan "
                                              "sebagai data latih untuk pembaruan model berikutnya.")
        left, right = st.columns(2, gap="medium")
        slang = left.text_input("Istilah slang", key=f"add_slang_{form_id}", placeholder="contoh: rungkad")
        baku = right.text_input("Padanan baku", key=f"add_baku_{form_id}", placeholder="contoh: hancur")
        pairs = _example_rows(form_id)
        error = st.empty()
        with st.container(key="adm_add_actions", horizontal=True, horizontal_alignment="right", gap="small"):
            if st.button("Kosongkan", key="adm_add_reset"):
                _reset_add_form()
                st.rerun(scope="fragment")
            if st.button("Simpan ke Kamus", type="primary", key="adm_add_save", disabled=disabled):
                _save_new_term(slang, baku, pairs, error)


@st.dialog("Ubah istilah")
def _edit_dialog(slang: str) -> None:
    kamus = load_kamus()
    matches = kamus.index[kamus["slang"] == slang]
    if matches.empty:
        st.rerun()
    index = matches[0]
    _dialog_heading("pencil", "blue", "Ubah istilah", "Perubahan langsung dipakai lexical mapping.")
    new_slang = st.text_input("Istilah slang", value=slang, key=f"edit_slang_{slang}")
    new_baku = st.text_input("Padanan baku", value=kamus.at[index, "baku"], key=f"edit_baku_{slang}")
    error = st.empty()
    with st.container(key="dlg_actions", horizontal=True, horizontal_alignment="center"):
        if st.button("Batal", key="dlg_edit_cancel"):
            st.rerun()
        if not st.button("Simpan", type="primary", key="dlg_edit_save"):
            return

    new_slang = _normalize(new_slang).lower()
    new_baku = _normalize(new_baku)
    problem = _term_problem(new_slang, kamus.drop(index=index)) or (None if new_baku else "Padanan baku wajib diisi.")
    if problem:
        _field_error(error, problem)
        return

    kamus.loc[index, ["slang", "baku"]] = [new_slang, new_baku]
    warnings = [save_kamus(kamus)]
    data = load_data_baru()
    if new_slang != slang and (data["istilah"] == slang).any():
        data.loc[data["istilah"] == slang, "istilah"] = new_slang
        warnings.append(save_data_baru(data))
    _flash(f'Istilah "{new_slang}" diperbarui.', warnings)
    st.rerun()


@st.dialog("Hapus istilah?")
def _delete_dialog(slang: str) -> None:
    data = load_data_baru()
    count = int((data["istilah"] == slang).sum())
    message = f"Istilah <b>{html.escape(slang)}</b> akan dihapus dari kamus."
    if count:
        message += f" {count} contoh kalimat istilah ini di Data Latih Baru juga ikut dihapus."
    _dialog_heading("trash", "red", "Hapus istilah?", message)
    with st.container(key="dlg_actions", horizontal=True, horizontal_alignment="center"):
        if st.button("Kembali", key="dlg_back"):
            st.rerun()
        if st.button("Ya, Hapus", type="primary", key="dlg_yes"):
            kamus = load_kamus()
            warnings = [save_kamus(kamus[kamus["slang"] != slang])]
            if count:
                warnings.append(save_data_baru(data[data["istilah"] != slang]))
            _flash(f'Istilah "{slang}" dihapus.', warnings)
            st.rerun()


def _list_page(query: str, total_pages: int) -> int:
    if st.session_state.get(LIST_QUERY_KEY) != query:
        st.session_state[LIST_QUERY_KEY] = query
        st.session_state[LIST_PAGE_KEY] = 1
    page = min(max(1, st.session_state.get(LIST_PAGE_KEY, 1)), total_pages)
    st.session_state[LIST_PAGE_KEY] = page
    return page


def _term_cell(row) -> str:
    badge = '<span class="badge-new">Baru</span>' if is_new(row.ditambahkan) else ""
    return f'<div class="row-slang">{html.escape(row.slang)}{badge}</div>'


@st.fragment
def _kamus_list(disabled: bool) -> None:
    kamus = load_kamus()
    with st.container(key="adm_list"):
        with st.container(key="adm_list_head", horizontal=True, vertical_alignment="bottom", gap="small"):
            last = kamus["ditambahkan"].dropna().astype(str)
            subtitle = f"{len(kamus)} istilah"
            if len(last):
                subtitle += f" · terakhir ditambahkan {format_date(last.max())}"
            _section_heading("Daftar Kamus", subtitle)
            query = st.text_input("Cari istilah di kamus", placeholder="Cari istilah...", icon=":material/search:",
                                  label_visibility="collapsed", key="adm_search", live=SEARCH_DELAY, width=280)

        view = kamus
        if query.strip():
            view = view[view["slang"].str.contains(query.strip(), case=False, regex=False)]
        total_pages = max(1, math.ceil(len(view) / PAGE_SIZE))
        page = _list_page(query, total_pages)
        start = (page - 1) * PAGE_SIZE

        st.markdown('<div class="row-head"><span>No</span><span>Istilah Slang</span><span>Padanan Baku</span>'
                    '<span>Ditambahkan</span><span>Aksi</span></div>', unsafe_allow_html=True)
        if view.empty:
            st.markdown('<div class="row-empty">Istilah tidak ditemukan.</div>', unsafe_allow_html=True)
        for number, row in enumerate(view.iloc[start:start + PAGE_SIZE].itertuples(), start=start + 1):
            with st.container(key=f"adm_row_{number}", horizontal=True, vertical_alignment="center", gap="small"):
                st.markdown(f'<div class="row-num">{number}</div>', unsafe_allow_html=True, width=36)
                st.markdown(_term_cell(row), unsafe_allow_html=True, width="stretch")
                st.markdown(f'<div class="row-text">{html.escape(row.baku)}</div>', unsafe_allow_html=True,
                            width="stretch")
                st.markdown(f'<div class="row-date">{format_date(row.ditambahkan)}</div>', unsafe_allow_html=True,
                            width=110)
                if st.button("", icon=":material/edit:", key=f"adm_edit_{number}", disabled=disabled):
                    _edit_dialog(row.slang)
                if st.button("", icon=":material/delete:", key=f"adm_del_{number}", disabled=disabled):
                    _delete_dialog(row.slang)
        if total_pages > 1:
            pager("adm_pager", LIST_PAGE_KEY, page, total_pages)


# =============================================================================
# TAB 2: DATA LATIH BARU
# =============================================================================
def _stat(label: str, value, note: str) -> str:
    return (f'<div class="adm-stat"><span>{html.escape(label)}</span><b>{html.escape(str(value))}</b>'
            f'<small>{html.escape(note)}</small></div>')


@st.fragment
def _data_table(data: pd.DataFrame) -> None:
    view = data.iloc[::-1].reset_index(drop=True)
    total_pages = max(1, math.ceil(len(view) / PAGE_SIZE))
    page = min(max(1, st.session_state.get(DATA_PAGE_KEY, 1)), total_pages)
    start = (page - 1) * PAGE_SIZE
    rows = [[start + i + 1, r.clean_comment, r.baku_reference, r.istilah, format_date(r.ditambahkan, "-")]
            for i, r in enumerate(view.iloc[start:start + PAGE_SIZE].itertuples())]
    st.markdown(html_table(DATA_HEADERS, rows, DATA_CLASSES, widths=DATA_WIDTHS,
                           empty_text="Belum ada contoh kalimat. Tambahkan slang baru di tab Kelola Kamus."),
                unsafe_allow_html=True)
    if total_pages > 1:
        pager("adm_data_pager", DATA_PAGE_KEY, page, total_pages)


def _data_tab() -> None:
    data = load_data_baru()
    terms = list(dict.fromkeys(data["istilah"][data["istilah"] != ""]))
    shown_terms = ", ".join(terms[:4]) + (f", +{len(terms) - 4} lainnya" if len(terms) > 4 else "")
    model_id, revision = active_model()
    info = _model_info(model_id, revision)
    updated = format_date(info["last_modified"], "-") if info else "-"
    st.markdown('<div class="adm-stats">'
                + _stat("Contoh kalimat terkumpul", len(data), "pasangan kalimat slang → baku")
                + _stat("Istilah yang dicakup", len(terms), shown_terms or "belum ada")
                + _stat("Model aktif diperbarui", updated, f"{model_id}@{revision}")
                + '</div>', unsafe_allow_html=True)

    with st.container(key="adm_data"):
        with st.container(key="adm_data_head", horizontal=True, vertical_alignment="center", gap="small"):
            _section_heading("Contoh Kalimat Terkumpul",
                             "Diunduh sebagai data_baru.csv untuk notebook fine-tuning lanjutan")
            st.download_button("Download data_baru.csv", data=data.to_csv(index=False).encode("utf-8"),
                               file_name="data_baru.csv", mime="text/csv", type="primary",
                               icon=":material/download:", on_click="ignore", disabled=data.empty,
                               key="adm_dl_data")
        _data_table(data)


# =============================================================================
# TAB 3: PEMBARUAN MODEL
# =============================================================================
@st.cache_data(ttl=600, show_spinner=False)
def _model_info(model_id: str, revision: str) -> dict | None:
    path = Path(model_id)
    if path.is_dir():
        modified = datetime.fromtimestamp(path.stat().st_mtime, TIMEZONE)
        return {"sha": "folder lokal", "last_modified": modified.date().isoformat()}
    try:
        from huggingface_hub import HfApi
        info = HfApi(token=get_secret("HF_TOKEN")).model_info(model_id, revision=revision)
    except Exception:
        return None
    modified = info.last_modified.astimezone(TIMEZONE).date().isoformat() if info.last_modified else None
    return {"sha": (info.sha or "")[:7], "last_modified": modified}


def _model_problem(model_id: str, revision: str) -> str | None:
    if Path(model_id).is_dir():
        return None
    try:
        from huggingface_hub import HfApi
        from huggingface_hub.errors import RepositoryNotFoundError, RevisionNotFoundError
        HfApi(token=get_secret("HF_TOKEN")).model_info(model_id, revision=revision)
    except (RepositoryNotFoundError, RevisionNotFoundError):
        return (f'Model "{model_id}" versi "{revision}" tidak ditemukan di Hugging Face. '
                f"Periksa penulisan Model ID dan versinya.")
    except Exception as e:
        return f"Tidak dapat menghubungi Hugging Face: {str(e).splitlines()[0][:150]}"
    return None


def _notebook_bytes(model_id: str) -> bytes:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    if not Path(model_id).is_dir():
        for cell in notebook["cells"]:
            if cell["cell_type"] != "code":
                continue
            source = cell["source"]
            replace = lambda text: NOTEBOOK_MODEL_RE.sub(lambda m: f'{m.group(1)} = "{model_id}"', text)
            cell["source"] = replace(source) if isinstance(source, str) else [replace(line) for line in source]
    return json.dumps(notebook, ensure_ascii=False, indent=1).encode("utf-8")


def _reload_clicked() -> None:
    reload_model()
    _model_info.clear()
    _flash("Model dimuat ulang.")


def _active_model_card() -> None:
    model_id, revision = active_model()
    _, error = load_mt5()
    info = _model_info(model_id, revision)
    version = f"{revision} · {info['sha']}" if info and info["sha"] else revision
    updated = format_date(info["last_modified"], "-") if info else "-"
    status = ('<span class="adm-chip err">Gagal dimuat</span>' if error
              else '<span class="adm-chip ok">Dimuat</span>')

    with st.container(key="adm_model"):
        with st.container(key="adm_model_head", horizontal=True, vertical_alignment="center"):
            _section_heading("Model Aktif")
            st.markdown(status, unsafe_allow_html=True, width="content")
        st.markdown(f'<div class="adm-grid">'
                    f'<div><span>Model ID</span><code>{html.escape(model_id)}</code></div>'
                    f'<div><span>Versi</span><code>{html.escape(version)}</code></div>'
                    f'<div><span>Diperbarui di Hugging Face</span><b>{updated}</b></div></div>',
                    unsafe_allow_html=True)
        if error:
            st.error(error)
        with st.container(horizontal=True, horizontal_alignment="right"):
            st.button("Muat Ulang Model", icon=":material/refresh:", key="adm_reload", on_click=_reload_clicked)


STEPS = [
    ("Unduh notebook & data", "Notebook dan kamus terbaru di bawah, data_baru.csv di tab Data Latih Baru."),
    ("Jalankan di Colab", "Pilih GPU T4, lalu jalankan semua sel. Model dilatih lanjut dari model aktif."),
    ("Periksa evaluasi", "Bandingkan model lama dan baru di data uji lama dan baru, lalu unggah ke Hugging Face."),
    ("Aktifkan di aplikasi", "Klik Muat Ulang Model, atau isi Model ID dan versi baru di Ganti Model."),
]


def _training_card() -> None:
    model_id, _ = active_model()
    steps = "".join(f'<li><span class="step-num">{n}</span><b>{html.escape(title)}</b>'
                    f'<small>{html.escape(text)}</small></li>' for n, (title, text) in enumerate(STEPS, start=1))
    with st.container(key="adm_steps"):
        _section_heading("Melatih Ulang Model", "Pelatihan memerlukan GPU, sehingga dijalankan di Google Colab "
                                                "dengan notebook fine-tuning lanjutan.")
        st.markdown(f'<ol class="adm-steps">{steps}</ol>', unsafe_allow_html=True)
        with st.container(horizontal=True, horizontal_alignment="right", gap="small"):
            st.download_button("Download Kamus", data=kamus_bytes(), file_name="Kamus_Slang_Game.xlsx",
                               mime=XLSX_MIME, icon=":material/download:", on_click="ignore", key="adm_dl_kamus")
            st.download_button("Download Notebook",
                               data=_notebook_bytes(model_id) if NOTEBOOK_PATH.exists() else b"",
                               file_name=NOTEBOOK_NAME, mime="application/x-ipynb+json", type="primary",
                               icon=":material/download:", on_click="ignore", disabled=not NOTEBOOK_PATH.exists(),
                               key="adm_dl_notebook")


def _reset_model_form() -> None:
    st.session_state[MODEL_FORM_KEY] = st.session_state.get(MODEL_FORM_KEY, 0) + 1


def _switch_model(model_id: str, revision: str, error) -> None:
    model_id, revision = model_id.strip(), revision.strip() or "main"
    problem = "Model ID wajib diisi." if not model_id else _model_problem(model_id, revision)
    if problem:
        _field_error(error, problem)
        return

    previous = active_model()
    warning = set_active_model(model_id, revision)
    reload_model()
    _, load_error = load_mt5()
    if load_error:
        set_active_model(*previous)
        reload_model()
        load_mt5()
        _field_error(error, f"Model baru gagal dimuat, model sebelumnya tetap dipakai. {load_error}")
        return
    _model_info.clear()
    _reset_model_form()
    _flash(f'Model "{model_id}@{revision}" sekarang aktif.', [warning])
    st.rerun()


def _change_model_card(disabled: bool) -> None:
    model_id, revision = active_model()
    form_id = st.session_state.get(MODEL_FORM_KEY, 0)
    with st.container(key="adm_change"):
        _section_heading("Ganti Model", "Model bisa berasal dari akun Hugging Face mana pun. "
                                        "Kode aplikasi tidak perlu diubah.")
        left, right = st.columns([2, 1], gap="medium")
        new_id = left.text_input("Model ID", value=model_id, key=f"adm_model_id_{form_id}")
        new_revision = right.text_input("Versi (revision)", value=revision, key=f"adm_model_rev_{form_id}",
                                        help="Isi main untuk versi terbaru, atau kode commit untuk versi tertentu.")
        st.markdown(f'<div class="adm-hint">{svg("alert", 16)}<span>Aktifkan model baru hanya jika hasil '
                    f'evaluasinya tidak lebih buruk dari model lama. Untuk kembali ke versi sebelumnya, isi kode '
                    f'commit versi lama dari Hugging Face.</span></div>', unsafe_allow_html=True)
        error = st.empty()
        with st.container(horizontal=True, horizontal_alignment="right", gap="small"):
            st.button("Batal", key="adm_model_cancel", on_click=_reset_model_form)
            if st.button("Simpan & Muat Ulang", type="primary", icon=":material/check:", key="adm_model_save",
                         disabled=disabled):
                with st.spinner("Memeriksa dan memuat model..."):
                    _switch_model(new_id, new_revision, error)


# =============================================================================
# HALAMAN
# =============================================================================
def _logout() -> None:
    st.session_state[ADMIN_KEY] = False
    st.switch_page(st.session_state[PAGES_KEY]["dict"])


def _storage_notice() -> bool:
    error = store_error()
    if error:
        st.error(f"{error}. Penyimpanan dinonaktifkan agar data di Hugging Face tidak tertimpa.")
        if st.button("Coba Lagi", icon=":material/refresh:", key="adm_store_retry"):
            refresh_store()
            st.rerun()
        return False
    if not remote_storage():
        st.info("Data admin disimpan di folder aplikasi. Di Streamlit Cloud, perubahan akan hilang saat aplikasi "
                "di-reboot. Isi DATA_REPO dan HF_TOKEN di Secrets agar tersimpan permanen di Hugging Face.")
    return True


def _locked_page() -> None:
    page_header("Panel Admin", "Halaman ini hanya dapat dibuka oleh admin")
    st.info("Silakan masuk sebagai admin terlebih dahulu.")
    if st.button("Masuk sebagai Admin", type="primary", icon=":material/lock:", key="adm_locked_login"):
        login_dialog()


def render() -> None:
    if not is_admin():
        _locked_page()
        return
    st.session_state.pop(GO_ADMIN_KEY, None)

    with header_with_actions("Panel Admin", "Kelola kamus slang game, data latih baru, dan pembaruan model",
                             "adm_head"):
        st.markdown('<div class="adm-user"><span></span>Masuk sebagai<b>admin</b></div>', unsafe_allow_html=True,
                    width="content")
        if st.button("Keluar", icon=":material/logout:", key="adm_logout"):
            _logout()
    _show_flash()
    can_save = _storage_notice()

    kamus_tab, data_tab, model_tab = st.tabs(["Kelola Kamus", "Data Latih Baru", "Pembaruan Model"],
                                             key="adm_tab")
    with kamus_tab:
        _add_form(not can_save)
        _kamus_list(not can_save)
    with data_tab:
        _data_tab()
    with model_tab:
        _active_model_card()
        _training_card()
        _change_model_card(not can_save)