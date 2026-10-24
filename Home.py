"""Home.py"""
import importlib.util
import sys
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "Assets"
IMAGES = {
    "light": {"background": ASSETS_DIR / "LightGameBackground.jpg", "hero": ASSETS_DIR / "PokemonBackground.jpg"},
    "dark": {"background": ASSETS_DIR / "IndieGameBackground.jpg", "hero": ASSETS_DIR / "Charizard.jpg"},
}
sys.path.insert(0, str(BASE_DIR))

st.set_page_config(page_title="Slang Game Normalizer", page_icon="🎮", layout="wide",
                   initial_sidebar_state="expanded")

from Pages import comment_translator, dictionary_slang_game, text_translator
from Pages.text_translator import image_data_uri, svg

DARK_MODE_KEY = "dark_mode"
SIDEBAR_OPEN_KEY = "sidebar_open"
PAGES_KEY = "PAGES"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

help_about = load_module(BASE_DIR / "Pages" / "help&about.py", "help_about")

def _theme_image(kind: str) -> Path | None:
    theme = "dark" if st.session_state.get(DARK_MODE_KEY, False) else "light"
    image = IMAGES[theme][kind]
    return image if image.exists() else None

def _background_css() -> str:
    image = _theme_image("background")
    if image is None:
        return ""
    return (f'.stApp {{ background-image: linear-gradient(var(--bg-overlay), var(--bg-overlay)), '
            f'url("{image_data_uri(image)}"); }}')

def load_css() -> None:
    css = (BASE_DIR / "Style.css").read_text(encoding="utf-8") + _background_css()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# =============================================================================
# HALAMAN 1: BERANDA
# =============================================================================
def _hero() -> None:
    with st.container(border=True, key="hero"):
        left, right = st.columns([1.45, 1], vertical_alignment="center", gap="large")
        with left:
            st.markdown(
                """<div class="eyebrow">SELAMAT DATANG DI</div>
                   <h1 class="hero-title">Slang Game <span class="hl">Normalizer</span></h1>
                   <p class="hero-desc">Menerjemahkan istilah gaul, singkatan, dan jargon game <br>
                   menjadi bahasa Indonesia baku.</p>""",
                unsafe_allow_html=True,
            )
        with right:
            image = _theme_image("hero")
            if image:
                st.markdown(f'<img class="hero-img" src="{image_data_uri(image)}" alt="Ilustrasi setup gaming">',
                            unsafe_allow_html=True)
            else:
                st.markdown('<div class="hero-placeholder">Gambar hero tidak ditemukan di folder Assets/</div>',
                            unsafe_allow_html=True)

def _feature_card(key: str, icon: str, tone: str, title: str, description: str, page, label: str) -> None:
    with st.container(border=True, key=key):
        st.markdown(
            f"""<div class="feat-icon {tone}">{svg(icon)}</div>
                <div class="feat-title">{title}</div>
                <div class="feat-desc">{description}</div>""",
            unsafe_allow_html=True,
        )
        st.page_link(page, label=label)

def home_page() -> None:
    pages = st.session_state[PAGES_KEY]
    _hero()
    st.write("")

    features = [
        ("feat_text", "doc", "blue", "Text Translator",
         "Terjemahkan langsung paragraf teks, obrolan chat, atau deskripsi game yang penuh dengan "
         "bahasa slang menjadi teks formal secara instan.", pages["text"], "Gunakan Sekarang"),
        ("feat_comment", "chat", "gray", "Comment Translator",
         "Unggah berkas CSV/XLS berisi ratusan komentar untuk dinormalisasi dari file.",
         pages["comment"], "Gunakan Sekarang"),
        ("feat_dict", "filesearch", "amber", "Dictionary Slang Game",
         "Cari kamus komprehensif istilah slang game Indonesia (seperti Noob, GG, AFK, Savage) "
         "lengkap dengan arti dan padanan kata bakunya.", pages["dict"], "Lihat Kamus"),
    ]
    for column, feature in zip(st.columns(3, gap="medium"), features):
        with column:
            _feature_card(*feature)


# =============================================================================
# NAVIGASI
# =============================================================================
def build_pages() -> dict:
    return {
        "home": st.Page(home_page, title="Home", icon=":material/home:", url_path="beranda", default=True),
        "text": st.Page(text_translator.render, title="Text Translator", icon=":material/description:",
                        url_path="text-translator"),
        "comment": st.Page(comment_translator.render, title="Comment Translator",
                           icon=":material/chat_bubble_outline:", url_path="comment-translator"),
        "dict": st.Page(dictionary_slang_game.render, title="Dictionary Slang Game", icon=":material/menu_book:",
                        url_path="dictionary"),
        "about": st.Page(help_about.render_about, title="About", url_path="tentang"),
        "help": st.Page(help_about.render_help, title="Help", url_path="bantuan"),
    }


# =============================================================================
# SIDEBAR
# =============================================================================
MAIN_MENU = ("home", "text", "comment", "dict")
EXTRA_MENU = ("about", "help")

def _menu_link(pages: dict, key: str, group: str, current_title: str) -> None:
    state = "act" if current_title == pages[key].title else ""
    with st.container(key=f"{group}{state}_{key}"):
        st.page_link(pages[key])

def _state_markers() -> None:
    if st.session_state.get(DARK_MODE_KEY, False):
        st.markdown('<div class="dark-mode-on"></div>', unsafe_allow_html=True)
    if not st.session_state.get(SIDEBAR_OPEN_KEY, True):
        st.markdown('<div class="sidebar-closed"></div>', unsafe_allow_html=True)

def render_sidebar(pages: dict, current_title: str) -> None:
    with st.sidebar:
        st.markdown(
            f"""<div class="brand">
                  <div class="brand-logo">{svg('gamepad', 22)}</div>
                  <div class="brand-name">Slang Game <span>Normalizer</span></div>
                </div>""",
            unsafe_allow_html=True,
        )
        for key in MAIN_MENU:
            _menu_link(pages, key, "nav", current_title)
        st.markdown('<hr class="side-divider">', unsafe_allow_html=True)
        for key in EXTRA_MENU:
            _menu_link(pages, key, "navsub", current_title)
        _state_markers()


# =============================================================================
# TOMBOL POJOK ATAS
# =============================================================================
def _toggle(key: str, default: bool) -> None:
    st.session_state[key] = not st.session_state.get(key, default)

def render_corner_buttons() -> None:
    sidebar_open = st.session_state.get(SIDEBAR_OPEN_KEY, True)
    dark_mode = st.session_state.get(DARK_MODE_KEY, False)
    st.button("", key="side_btn", on_click=_toggle, args=(SIDEBAR_OPEN_KEY, True),
              icon=":material/menu_open:" if sidebar_open else ":material/menu:")
    st.button("", key="theme_btn", on_click=_toggle, args=(DARK_MODE_KEY, False),
              icon=":material/light_mode:" if dark_mode else ":material/dark_mode:")


# =============================================================================
# JALANKAN
# =============================================================================
load_css()
PAGES = build_pages()
st.session_state[PAGES_KEY] = PAGES
navigation = st.navigation(list(PAGES.values()), position="hidden")

render_sidebar(PAGES, navigation.title)
render_corner_buttons()
navigation.run()