"""App.py"""
import argparse
import os
import re
import time
from pathlib import Path
from typing import NamedTuple
import pandas as pd
import streamlit as st

def _run_by_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx(suppress_warning=True) is not None
    except Exception:
        return False

if __name__ == "__main__" and not _run_by_streamlit():
    import streamlit.logger
    streamlit.logger.set_log_level("error")


# =============================================================================
# PENGATURAN — ubah nilai di bagian ini sesuai kebutuhan
# =============================================================================
BASE_DIR = Path(__file__).parent

KAMUS_PATH = BASE_DIR / "Kamus_Slang_Game.xlsx"
KAMUS_CSV_FALLBACK = BASE_DIR / "KamusSlangGame.csv"

MODEL_ID = os.getenv("MT5_MODEL_ID", "Brnalxz/mt5-small-normalisasi-slang-game")
MODEL_REVISION = os.getenv("MT5_MODEL_REVISION", "main")

SHOW_MODEL_INFO = False
TASK_PREFIX = "normalisasi teks game ke bahasa Indonesia baku: "
MAX_INPUT_LEN = 128
MAX_NEW_TOKENS = 128
NUM_BEAMS = 4
BATCH_SIZE = 16
CHUNK_WORDS = 40


# =============================================================================
# 1. KAMUS
# =============================================================================
MAX_PHRASE_WORDS = 4


@st.cache_data(show_spinner=False)
def _read_kamus_file(path: str, modified_time: float) -> pd.DataFrame:
    if path.lower().endswith(".xlsx"):
        df = pd.read_excel(path, sheet_name=0)
    else:
        df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")

    df = df.iloc[:, :2].copy()
    df.columns = ["slang", "baku"]
    df = df.dropna()
    df["slang"] = df["slang"].astype(str).str.strip().str.lower()
    df["baku"] = df["baku"].astype(str).str.strip()
    df = df[(df["slang"] != "") & (df["baku"] != "")]
    return df.drop_duplicates(subset="slang").reset_index(drop=True)

def _kamus_file() -> Path:
    for path in (KAMUS_PATH, KAMUS_CSV_FALLBACK):
        if path.exists():
            return path
    raise FileNotFoundError(
        f"Kamus tidak ditemukan. Letakkan '{KAMUS_PATH.name}' di folder yang sama dengan App.py ({BASE_DIR})."
    )

def load_kamus() -> pd.DataFrame:
    path = _kamus_file()
    return _read_kamus_file(str(path), path.stat().st_mtime)

@st.cache_data(show_spinner=False)
def _build_mapping(df: pd.DataFrame) -> tuple[dict, int]:
    mapping = {}
    for slang, baku in zip(df["slang"], df["baku"]):
        key = preprocess(slang)
        if key and key not in mapping:
            mapping[key] = baku
    longest = max((len(key.split()) for key in mapping), default=1)
    return mapping, min(longest, MAX_PHRASE_WORDS)

def get_kamus() -> tuple[dict, int]:
    return _build_mapping(load_kamus())


# =============================================================================
# 2. PREPROCESSING
# =============================================================================
EMOJI_RE = re.compile(
    "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+",
    flags=re.UNICODE,
)
URL_RE = re.compile(r"(https?://\S+|www\.\S+)")
MENTION_RE = re.compile(r"[@#]\w+")
REPEATED_LETTER_RE = re.compile(r"([a-z])\1{2,}")
NON_ALPHANUMERIC_RE = re.compile(r"[^a-z0-9\s]")
WHITESPACE_RE = re.compile(r"\s+")

def preprocess(text) -> str:
    text = "" if pd.isna(text) else str(text)
    text = text.lower()
    text = URL_RE.sub(" ", text)
    text = MENTION_RE.sub(" ", text)
    text = EMOJI_RE.sub(" ", text)
    text = REPEATED_LETTER_RE.sub(r"\1", text)
    text = NON_ALPHANUMERIC_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


# =============================================================================
# 3. LEXICAL MAPPING (post-processing keluaran mT5)
# =============================================================================
EDGE_PUNCTUATION_RE = re.compile(r"^(\W*)(.*?)(\W*)$", flags=re.UNICODE)
SENTENCE_END = (".", "!", "?")

class _Token(NamedTuple):
    lead: str
    word: str
    trail: str
    key: str

def _tokenize(text: str) -> list[_Token]:
    tokens = []
    for raw in text.split():
        lead, word, trail = EDGE_PUNCTUATION_RE.match(raw).groups()
        tokens.append(_Token(lead, word, trail, preprocess(word)))
    return tokens

def _phrase_key(span: list[_Token]) -> str:
    punctuation_inside = any(t.trail for t in span[:-1]) or any(t.lead for t in span[1:])
    if punctuation_inside:
        return ""
    return " ".join(t.key for t in span if t.key)

def _longest_match(tokens: list[_Token], start: int, mapping: dict, max_words: int) -> tuple[int, str]:
    for length in range(min(max_words, len(tokens) - start), 0, -1):
        key = _phrase_key(tokens[start:start + length])
        if key and key in mapping:
            return length, mapping[key]
    return 0, ""

def _match_capitalization(original_word: str, replacement: str, at_sentence_start: bool) -> str:
    starts_upper = original_word[:1].isupper()
    is_acronym = original_word.isupper()
    if starts_upper and (at_sentence_start or not is_acronym):
        return replacement[:1].upper() + replacement[1:]
    return replacement

def lexical_map(text: str) -> str:
    mapping, max_words = get_kamus()
    tokens = _tokenize(text)
    output, i = [], 0
    while i < len(tokens):
        length, baku = _longest_match(tokens, i, mapping, max_words)
        if length:
            at_sentence_start = i == 0 or tokens[i - 1].trail.endswith(SENTENCE_END)
            baku = _match_capitalization(tokens[i].word, baku, at_sentence_start)
            output.append(tokens[i].lead + baku + tokens[i + length - 1].trail)
            i += length
        else:
            output.append(tokens[i].lead + tokens[i].word + tokens[i].trail)
            i += 1
    return " ".join(output)


# =============================================================================
# 4. MODEL mT5 — memuat dari Hugging Face dan menjalankan model
# =============================================================================
LIBRARY_MISSING_MSG = "Library belum terpasang ({}). Jalankan: pip install -r requirements.txt"

# ---- 4a. Memuat model ----
def _hf_token() -> str | None:
    token = os.getenv("HF_TOKEN")
    if token:
        return token
    try:
        return st.secrets.get("HF_TOKEN")
    except Exception:
        return None

def _describe_load_error(error: Exception) -> str:
    text = str(error).strip()
    message = text.splitlines()[0][:300] if text else type(error).__name__
    if "sentencepiece" in text.lower() or "protobuf" in text.lower():
        message += " -> Jalankan: pip install sentencepiece protobuf"
    elif "Can't load" in text or "huggingface.co" in text or "connect" in text.lower():
        message = (f"tidak bisa mengunduh dari Hugging Face. Periksa koneksi internet dan nama MODEL_ID "
                   f"(repo private butuh HF_TOKEN). Detail: {message[:150]}")
    return f"Model '{MODEL_ID}' gagal dimuat: {message}"

def _format_param_count(count: int) -> str:
    return f"{count / 1e6:.0f} juta parameter" if count >= 1e6 else f"{count / 1e3:.0f} ribu parameter"

@st.cache_resource(show_spinner="Memuat model mT5 dari Hugging Face...")
def _load_model_cached(model_id: str, revision: str):
    try:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except ImportError as e:
        return None, LIBRARY_MISSING_MSG.format(e.name)

    options = {"revision": revision, "token": _hf_token()}
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id, **options)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_id, **options)
    except Exception as e:
        return None, _describe_load_error(e)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()
    info = {"model_id": f"{model_id}@{revision}", "device": device,
            "params": _format_param_count(sum(p.numel() for p in model.parameters()))}
    return {"tokenizer": tokenizer, "model": model, "device": device, "info": info}, None

def load_mt5():
    if not MODEL_ID.strip():
        return None, "MODEL_ID di App.py belum diisi."
    return _load_model_cached(MODEL_ID, MODEL_REVISION)

def engine_info() -> str | None:
    bundle, error = load_mt5()
    if error:
        return None
    info = bundle["info"]
    return f"Model mT5 Hugging Face: {info['model_id']} · {info['params']} · {info['device'].upper()}"

def engine_status() -> tuple[bool, str | None]:
    _, error = load_mt5()
    if error:
        error = error if error.endswith(".") else error + "."
        return False, f"{error} Sementara hasil hanya melalui preprocessing dan lexical mapping (kamus)."
    return True, (engine_info() if SHOW_MODEL_INFO else None)

# ---- 4b. Menjalankan model ----
def mt5_generate(texts: list[str]) -> list[str]:
    import torch

    bundle, _ = load_mt5()
    tokenizer, model, device = bundle["tokenizer"], bundle["model"], bundle["device"]
    results = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = [TASK_PREFIX + t for t in texts[start:start + BATCH_SIZE]]
        encoded = tokenizer(batch, return_tensors="pt", padding=True, truncation=True,
                            max_length=MAX_INPUT_LEN).to(device)
        with torch.no_grad():
            output = model.generate(**encoded, max_new_tokens=MAX_NEW_TOKENS, num_beams=NUM_BEAMS, use_cache=True)
        results.extend(tokenizer.batch_decode(output, skip_special_tokens=True))
    return [r.strip() for r in results]


# =============================================================================
# 5. PIPELINE — fungsi yang dipakai halaman
# =============================================================================
def _chunks(text: str) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + CHUNK_WORDS]) for i in range(0, len(words), CHUNK_WORDS)] or [""]

def _generate_in_chunks(texts: list[str]) -> list[str]:
    pieces, owners = [], []
    for index, text in enumerate(texts):
        if text:
            for piece in _chunks(text):
                pieces.append(piece)
                owners.append(index)

    generated = mt5_generate(pieces) if pieces else []
    parts = [[] for _ in texts]
    for index, source, output in zip(owners, pieces, generated):
        parts[index].append(output or source)
    return [" ".join(p) for p in parts]

def run_pipeline(texts: list) -> dict:
    model_ready, _ = engine_status()
    keys = ["" if pd.isna(t) else str(t) for t in texts]
    unique = list(dict.fromkeys(keys))

    preprocessed = [preprocess(t) for t in unique]
    model_output = _generate_in_chunks(preprocessed) if model_ready else preprocessed
    final = [lexical_map(t) for t in model_output]

    return {"keys": keys, "unique": unique, "pre": preprocessed,
            "mt5": model_output if model_ready else None, "final": final}

def normalize_batch(texts: list) -> list[str]:
    result = run_pipeline(texts)
    lookup = dict(zip(result["unique"], result["final"]))
    return [lookup[key] for key in result["keys"]]

def normalize_text(text) -> str:
    return normalize_batch([text])[0]
