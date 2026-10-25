"""Halaman 3: Comment Translator"""
import csv
import html
import io
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from App import engine_status, normalize_batch
from Pages.text_translator import html_table, loading_overlay, page_header, pager, svg

MAX_MB = 5
PAGE_SIZE = 10
ALLOWED_TYPES = ["csv", "xls", "xlsx"]
CSV_SEPARATORS = ",;\t|"
CSV_ENCODINGS = ("utf-8-sig", "latin-1")

HEADERS = ["No", "Komentar Asli", "Hasil Normalisasi Baku"]
COLUMN_CLASSES = ["num", "bold", ""]
WIDTHS = ["58px", "37%", None]

UPLOAD_KEY = "up_key"
ERROR_KEY = "ct_error"
PAGE_KEY = "ct_page"
PAGE_OWNER_KEY = "ct_page_owner"

TEMPLATE_NAME = "template_komentar"
TEMPLATE_COLUMN = "Komentar"
TEMPLATE_PLACEHOLDER = "Tulis komentar di sini (satu komentar per baris)"
TEMPLATE_HEADER_COLOR = "D3D3D3"
TEMPLATE_COLUMN_WIDTH = 60
XLSX_MIME ="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# =============================================================================
# MEMBACA BERKAS
# =============================================================================
def _detect_sep(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=CSV_SEPARATORS).delimiter
    except csv.Error:
        return ","


def _parse_csv(text: str) -> pd.DataFrame:
    try:
        return pd.read_csv(io.StringIO(text), sep=_detect_sep(text[:5000]), header=None, dtype=str)
    except pd.errors.ParserError:
        lines = [line for line in text.splitlines() if line.strip()]
        return pd.DataFrame({0: lines})


def _read_csv(raw: bytes) -> pd.DataFrame:
    last_error = None
    for encoding in CSV_ENCODINGS:
        try:
            return _parse_csv(raw.decode(encoding))
        except Exception as e:
            last_error = e
    raise last_error


def read_upload(file) -> pd.DataFrame:
    if file.name.lower().endswith(".csv"):
        df = _read_csv(file.getvalue())
    else:
        file.seek(0)
        df = pd.read_excel(file, header=None, dtype=str)
    return df.dropna(how="all").reset_index(drop=True)


def _is_template_header(value) -> bool:
    return pd.notna(value) and str(value).strip().lower() == TEMPLATE_COLUMN.lower()


def _is_placeholder(value: str) -> bool:
    return value.strip().lower() == TEMPLATE_PLACEHOLDER.lower()


def extract_comments(df: pd.DataFrame) -> list[str] | None:
    first_column = df.iloc[:, 0]
    for row in range(len(first_column)):
        if _is_template_header(first_column.iloc[row]):
            values = first_column.iloc[row + 1:].dropna().astype(str)
            return [value for value in values if value.strip() and not _is_placeholder(value)]
    return None


# =============================================================================
# NORMALISASI
# =============================================================================
@st.cache_data(show_spinner=False)
def normalize_many(texts: tuple) -> list:
    return normalize_batch(list(texts))


def reset_upload() -> None:
    st.session_state[UPLOAD_KEY] = st.session_state.get(UPLOAD_KEY, 0) + 1


# =============================================================================
# TEMPLATE BERKAS
# =============================================================================
@st.cache_data(show_spinner=False)
def template_excel() -> bytes:
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    excel = io.BytesIO()
    with pd.ExcelWriter(excel, engine="openpyxl") as writer:
        pd.DataFrame({TEMPLATE_COLUMN: [TEMPLATE_PLACEHOLDER]}).to_excel(writer, index=False)
        sheet = writer.sheets["Sheet1"]
        header = sheet["A1"]
        header.fill = PatternFill("solid", start_color=TEMPLATE_HEADER_COLOR)
        header.font = Font(bold=True, color="000000", size=12)
        header.alignment = Alignment(horizontal="center", vertical="center")
        line = Side(style="thin", color="A6A6A6")
        header.border = Border(left=line, right=line, top=line, bottom=line)
        sheet.column_dimensions["A"].width = TEMPLATE_COLUMN_WIDTH
        sheet.row_dimensions[1].height = 20
    return excel.getvalue()


# =============================================================================
# POPUP (st.dialog)
# =============================================================================
ERROR_TITLE = "Berkas tidak dapat diproses"
CANCEL_TITLE = "Batalkan hasil normalisasi?"


def _dialog_body(icon: str, tone: str, title: str, message: str) -> None:
    st.markdown(f'<div class="dlg-icon {tone}">{svg(icon, 32)}</div>'
                f'<div class="dlg-title">{html.escape(title)}</div>'
                f'<div class="dlg-text">{html.escape(message)}</div>', unsafe_allow_html=True)


@st.dialog(ERROR_TITLE)
def _error_dialog(message: str, offer_template: bool) -> None:
    _dialog_body("alert", "red", ERROR_TITLE, message)
    with st.container(key="dlg_actions", horizontal=True, horizontal_alignment="center"):
        if offer_template:
            st.download_button("DOWNLOAD TEMPLATE", data=template_excel(), file_name=f"{TEMPLATE_NAME}.xlsx",
                               mime=XLSX_MIME, icon=":material/download:", on_click="ignore", key="dlg_template")
        if st.button("Mengerti", type="primary", key="dlg_ok"):
            st.rerun()


@st.dialog(CANCEL_TITLE)
def _cancel_dialog() -> None:
    _dialog_body("trash", "red", CANCEL_TITLE, "Berkas dan hasil normalisasi akan dihapus dari halaman ini. "
                                              "Pastikan hasilnya sudah diunduh jika masih dibutuhkan.")
    with st.container(key="dlg_actions", horizontal=True, horizontal_alignment="center"):
        if st.button("Kembali", key="dlg_back"):
            st.rerun()
        if st.button("Ya, Batalkan", type="primary", key="dlg_yes"):
            reset_upload()
            st.rerun()


def _fail(message: str, offer_template: bool = False) -> None:
    st.session_state[ERROR_KEY] = (message, offer_template)
    reset_upload()
    st.rerun()


# =============================================================================
# BAGIAN-BAGIAN HALAMAN
# =============================================================================
def _upload_area(upload_key: int):
    with st.container(key="upload_zone"):
        st.markdown(
            f"""<div class="up-icon">{svg('cloud', 26)}</div>
                <div class="up-title">Pilih Berkas atau Tarik ke Sini</div>
                <div class="up-sub">Mendukung format .CSV, .XLS, atau .XLSX (Maks. {MAX_MB}MB)</div>""",
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader("Masukkan File Disini", key=f"uploader_{upload_key}", label_visibility="collapsed")
        if uploaded is None:
            _template_button()
        return uploaded


def _template_button() -> None:
    with st.container(key="template_row", horizontal=True, horizontal_alignment="center"):
        st.download_button("DOWNLOAD TEMPLATE", data=template_excel(), file_name=f"{TEMPLATE_NAME}.xlsx",
                           mime=XLSX_MIME, type="tertiary", icon=":material/download:",
                           on_click="ignore", key="tpl_xlsx")


def _empty_result_card(message: str) -> None:
    with st.container(key="result_card"):
        st.markdown(html_table(HEADERS, [], COLUMN_CLASSES, empty_text=message, widths=WIDTHS),
                    unsafe_allow_html=True)


def _load_comments(uploaded) -> list[str]:
    extension = Path(uploaded.name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_TYPES:
        shown = f".{extension.upper()}" if extension else "tanpa ekstensi"
        _fail(f"Format berkas \"{uploaded.name}\" ({shown}) tidak didukung. "
              f"Gunakan berkas berformat .CSV, .XLS, atau .XLSX.")
    if uploaded.size > MAX_MB * 1024 * 1024:
        _fail(f"Ukuran berkas \"{uploaded.name}\" melebihi batas {MAX_MB}MB.")
    try:
        df = read_upload(uploaded)
    except pd.errors.EmptyDataError:
        _fail(f"Berkas \"{uploaded.name}\" kosong, tidak berisi data komentar.")
    except Exception:
        _fail(f"Berkas \"{uploaded.name}\" tidak dapat dibaca. Pastikan berkas tidak rusak "
              f"dan isinya berupa tabel komentar.")
    if df.empty or df.shape[1] == 0:
        _fail(f"Berkas \"{uploaded.name}\" kosong, tidak berisi data komentar.")

    comments = extract_comments(df)
    if comments is None:
        _fail(f"Tidak sesuai template. Judul \"{TEMPLATE_COLUMN}\" harus di kolom A.", offer_template=True)
    if not comments:
        _fail(f"Berkas \"{uploaded.name}\" belum berisi komentar. Isi komentar di bawah judul kolom "
              f"\"{TEMPLATE_COLUMN}\", satu komentar per baris.", offer_template=True)
    return comments


def _current_page(owner: str, total_pages: int) -> int:
    if st.session_state.get(PAGE_OWNER_KEY) != owner:
        st.session_state[PAGE_OWNER_KEY] = owner
        st.session_state[PAGE_KEY] = 1
    page = min(max(1, st.session_state.get(PAGE_KEY, 1)), total_pages)
    st.session_state[PAGE_KEY] = page
    return page


@st.fragment
def _result_card(result: pd.DataFrame, owner: str) -> None:
    total_pages = max(1, math.ceil(len(result) / PAGE_SIZE))
    page = _current_page(owner, total_pages)
    start = (page - 1) * PAGE_SIZE

    with st.container(key="result_card"):
        rows = result.iloc[start:start + PAGE_SIZE].values.tolist()
        st.markdown(html_table(HEADERS, rows, COLUMN_CLASSES, truncate=True, widths=WIDTHS),
                    unsafe_allow_html=True)
        if total_pages > 1:
            pager("ct_pager", PAGE_KEY, page, total_pages)

        with st.container(key="result_footer", horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f'<div class="total">Total: {len(result)} komentar</div>',
                        unsafe_allow_html=True, width="stretch")
            if st.button("Batal", key="cancel"):
                _cancel_dialog()
            st.download_button(
                "Download Hasil", data=result.to_csv(index=False).encode("utf-8-sig"),
                file_name="hasil_normalisasi.csv", mime="text/csv",
                type="primary", icon=":material/save:", key="download",
            )


# =============================================================================
# HALAMAN
# =============================================================================
def render() -> None:
    page_header("Comment Translator",
                "Unggah dokumen komentar obrolan secara masal dan normalisasi semuanya dalam sekali proses")
    error = st.session_state.pop(ERROR_KEY, None)
    if error:
        _error_dialog(*error)

    upload_key = st.session_state.get(UPLOAD_KEY, 0)
    uploaded = _upload_area(upload_key)
    st.markdown('<div class="section-title">Hasil Normalisasi</div>', unsafe_allow_html=True)

    if uploaded is None:
        _empty_result_card("Belum ada berkas yang diunggah.")
        return

    originals = _load_comments(uploaded)

    _, note = engine_status()
    if note:
        st.info(note)

    with loading_overlay(f"Menormalisasi {len(originals)} komentar..."):
        normalized = normalize_many(tuple(originals))

    _result_card(pd.DataFrame({
        HEADERS[0]: range(1, len(originals) + 1),
        HEADERS[1]: originals,
        HEADERS[2]: normalized,
    }), owner=str(upload_key))