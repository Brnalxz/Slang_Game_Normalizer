"""Halaman 5 (Tentang) dan Halaman 6 (Bantuan)."""
import html
from pathlib import Path

import streamlit as st

from App import load_kamus
from Pages.text_translator import image_data_uri, page_header, svg

# ======================= ISI DATA ANDA DI SINI =======================
NAMA_APLIKASI = "Slang Game Normalizer"
PEMBUAT = {"nama": "Brandon Alexander Jayadi", "keterangan": "NIM 535230088", "foto": "Student.png"}
PEMBIMBING = [
    {"nama": "Viny Christanti Mawardi, S.Kom., M.Kom.", "keterangan": "Dosen Pembimbing 1", "foto": "DosenPembimbing.jpg"},
    {"nama": "Daniel Jahja Surjawan, S.Kom., M. T.", "keterangan": "Dosen Pembimbing 2", "foto": "DosenPendamping.jpeg"},
]
INSTANSI = "Program Studi Teknik Informatika, Fakultas Teknologi Informasi, Universitas Tarumanagara"
TAHUN = "2026"
# ======================================================================

TIM_DIR = Path(__file__).resolve().parent.parent / "Assets"

USAGE_CARDS = [
    ("about_use_text", "doc", "blue", "Text Translator",
     "Cara tercepat menormalisasi satu kalimat atau paragraf.",
     ["Buka menu <b>Text Translator</b>.",
      "Ketik atau tempel teks slang (maks. 500 karakter).",
      "Klik <b>Normalisasi Teks</b>.",
      "Salin hasil dengan tombol <b>Salin Hasil</b>."],
     "text", "Buka Text Translator"),
    ("about_use_comment", "chat", "gray", "Comment Translator",
     "Normalisasi ratusan komentar sekaligus dari berkas.",
     ["Buka menu <b>Comment Translator</b>.",
      "Unggah berkas .CSV, .XLS, atau .XLSX (maks. 5MB).",
      "Klik <b>Download Hasil</b> untuk menyimpan hasil."],
     "comment", "Buka Comment Translator"),
    ("about_use_dict", "filesearch", "amber", "Dictionary Slang Game",
     "Cari arti dan padanan baku istilah slang game.",
     ["Buka menu <b>Dictionary Slang Game</b>.",
      "Ketik istilah di kotak pencarian; hasil muncul saat mengetik.",
      "Gunakan <b>Sebelumnya</b> / <b>Berikutnya</b> untuk berpindah halaman."],
     "dict", "Buka Kamus"),
]

FAQ = [
    ("Bagaimana cara menggunakan Text Translator?",
     "Buka menu **Text Translator**, ketik teks slang (maks. 500 karakter), "
     "klik **Normalisasi Teks**, lalu salin hasilnya dengan tombol **Salin Hasil**."),
    ("Bagaimana format berkas untuk Comment Translator?",
     "Berkas berformat .CSV, .XLS, atau .XLSX (maks. 5MB) dengan satu kolom berisi komentar."),
    ("Bagaimana cara membuat berkas untuk Comment Translator?",
     "Klik **Download Template**, isi komentar di bawah judul kolom **Komentar** (satu komentar per baris), "
     "simpan, lalu unggah berkas tersebut. Jika judul kolom tidak sesuai, akan muncul pesan kesalahan."),
    ("Bagaimana mengunduh hasil normalisasi?",
     "Setelah tabel hasil tampil, klik **Download Hasil**. Klik **Batal** untuk mengunggah berkas lain."),
    ("Apakah ada batasan jumlah komentar untuk Comment Translator?",
     "Tidak ada batasan jumlah komentar yang dapat dinormalisasi dalam satu kali pengunggahan. Tetapi maksimal ukuran berkas hanya 5MB."),
    ("Bagaimana cara mencari istilah slang di Dictionary Slang Game?",
     "Buka menu **Dictionary Slang Game**, ketik istilah slang di kotak pencarian, kemudian hasil akan muncul."),
]

PIPELINE_HTML = """
<div class="about-subtitle">Alur normalisasi</div>
<div class="pipeline">
  <div class="pipe-step"><div class="pipe-num">1</div><div class="pipe-title">Preprocessing</div>
    <div class="pipe-desc">Huruf kecil, hapus URL, mention, hashtag, emoji, dan tanda baca, rapikan huruf berulang
    ("mantappp" → "mantap").</div></div>
  <div class="pipe-arrow">→</div>
  <div class="pipe-step main"><div class="pipe-num">2</div><div class="pipe-title">Model mT5</div>
    <div class="pipe-desc">Model hasil <i>fine-tuning</i> mengubah kalimat slang menjadi kalimat baku.</div></div>
  <div class="pipe-arrow">→</div>
  <div class="pipe-step"><div class="pipe-num">3</div><div class="pipe-title">Lexical Mapping</div>
    <div class="pipe-desc"><i>Post-processing</i>: istilah slang yang masih tersisa diganti padanan bakunya
    dari kamus.</div></div>
</div>
"""


# =============================================================================
# HELPER
# =============================================================================
def _section_title(text: str) -> None:
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)


def _term_count() -> str:
    try:
        return f"{len(load_kamus()):,}".replace(",", ".")
    except FileNotFoundError:
        return "-"


def _avatar(nama: str, foto: str) -> str:
    photo = TIM_DIR / foto
    if foto and photo.exists():
        return f'<img class="person-photo" src="{image_data_uri(photo)}" alt="{html.escape(nama)}">'
    initials = "".join(word[0] for word in nama.split()[:2]).upper() or "?"
    return f'<div class="person-photo person-initials">{html.escape(initials)}</div>'

def _person(person: dict) -> str:
    return (f'<div class="person">{_avatar(person["nama"], person.get("foto", ""))}'
            f'<div class="person-name">{html.escape(person["nama"])}</div>'
            f'<div class="person-sub">{html.escape(person.get("keterangan", ""))}</div></div>')

def _usage_card(key, icon, tone, title, intro, steps, page, label) -> None:
    with st.container(border=True, key=key):
        items = "".join(f"<li>{step}</li>" for step in steps)
        st.markdown(
            f'<div class="feat-icon {tone}">{svg(icon)}</div>'
            f'<div class="feat-title">{title}</div>'
            f'<div class="about-text">{intro}</div><ol class="about-steps">{items}</ol>',
            unsafe_allow_html=True,
        )
        st.page_link(page, label=label)


# =============================================================================
# HALAMAN TENTANG
# =============================================================================
def _about_app_section() -> None:
    with st.container(border=True, key="about_model"):
        st.markdown(
            f"""
<div class="section-title" style="margin-top:0">Tentang Aplikasi</div>
<div class="about-text"><b>{NAMA_APLIKASI}</b> adalah aplikasi web untuk mengubah teks yang berisi istilah gaul,
singkatan, dan jargon komunitas gamer Indonesia menjadi bahasa Indonesia baku. Aplikasi ini memakai model
<b>mT5 (Multilingual T5)</b> yang telah di-<i>fine-tune</i> pada korpus paralel komentar slang game dan padanan
bakunya, lalu dilengkapi kamus slang game.</div>
{PIPELINE_HTML}""",
            unsafe_allow_html=True,
        )


def _usage_section() -> None:
    _section_title("Cara Penggunaan")
    pages = st.session_state["PAGES"]
    for column, card in zip(st.columns(3, gap="medium"), USAGE_CARDS):
        key, icon, tone, title, intro, steps, page_key, label = card
        with column:
            _usage_card(key, icon, tone, title, intro, steps, pages[page_key], label)


def _team_section() -> None:
    _section_title("Pembuat &amp; Dosen Pembimbing")
    left, right = st.columns([1, 2], gap="medium")
    with left:
        with st.container(border=True, key="about_creator"):
            st.markdown(f'<div class="about-subtitle center">Pembuat</div>{_person(PEMBUAT)}',
                        unsafe_allow_html=True)
    with right:
        with st.container(border=True, key="about_advisors"):
            people = "".join(_person(p) for p in PEMBIMBING)
            st.markdown(f'<div class="about-subtitle center">Dosen Pembimbing</div>'
                        f'<div class="person-row">{people}</div>', unsafe_allow_html=True)


def _footer() -> None:
    st.markdown(
        f'<div class="about-footer"><b>{NAMA_APLIKASI}</b> · Dikembangkan oleh {html.escape(PEMBUAT["nama"])}'
        f' · {html.escape(INSTANSI)} · {TAHUN}</div>',
        unsafe_allow_html=True,
    )


def render_about() -> None:
    page_header("Tentang", f"Mengenal lebih dekat {NAMA_APLIKASI}")
    _about_app_section()
    _usage_section()
    _team_section()
    _footer()


# =============================================================================
# HALAMAN BANTUAN
# =============================================================================
def render_help() -> None:
    page_header("Bantuan", "Panduan penggunaan dan pertanyaan yang sering diajukan")
    for i, (question, answer) in enumerate(FAQ):
        with st.expander(question, expanded=(i == 0)):
            st.write(answer)