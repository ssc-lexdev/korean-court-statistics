"""Shared utilities for GPT vision OCR. Responses are cached under the OCR cache directory so re-runs make no new
API calls.

API key (needed only when a request is not in the cache; never printed or stored):
- the environment variable OPENAI_API_KEY, or
- SCOURT_KEY_FILE = path to a text file holding the key alone, or a line 'chat gpt api - sk-...'.
Set SCOURT_CACHE_ONLY=1 to forbid API calls (reconstruction from the published model responses)."""
import base64
import hashlib
import json
import re
from pathlib import Path

import fitz  # PyMuPDF
from openai import OpenAI

# Cache root: local disk (avoids the I/O bottleneck of a network drive). Override with the SCOURT_CACHE env var.
import os  # noqa: E402
CACHE_ROOT = Path(os.environ.get("SCOURT_CACHE", Path.home() / ".cache" / "scourt_stats"))
CACHE = CACHE_ROOT / "ocr_cache"
CACHE.mkdir(parents=True, exist_ok=True)
MODEL = "gpt-5.5"
_client = None


def _api_key():
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    kf = os.environ.get("SCOURT_KEY_FILE")
    if kf:
        txt = Path(kf).read_text(encoding="utf-8")
        m = re.search(r"chat gpt api\s*-\s*(sk-\S+)", txt) or re.search(r"(sk-\S+)", txt)
        if m:
            return m.group(1)
    raise RuntimeError("No API key: set OPENAI_API_KEY (or SCOURT_KEY_FILE). Not needed when every request is cached.")


def client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=_api_key())
    return _client


PNG_CACHE = CACHE_ROOT / "png_cache"
PNG_CACHE.mkdir(parents=True, exist_ok=True)
_docs = {}


def _doc(pdf_path):
    """Open each PDF once and reuse it (repeated opens on a network drive are a bottleneck)."""
    pdf_path = str(pdf_path)
    if pdf_path not in _docs:
        _docs[pdf_path] = fitz.open(pdf_path)
    return _docs[pdf_path]


# Call log (optional): if SCOURT_CALL_LOG=<jsonl path> is set, every ask() records the model, prompt and image source.
# Replaying from the cache this yields, without any API call, a list of which cached response came from which
# model, prompt and page.
CALL_LOG = os.environ.get("SCOURT_CALL_LOG")
_png_src = {}


def _note_png(png, pdf_path, page_no, dpi):
    if CALL_LOG:
        _png_src[hashlib.sha256(png).hexdigest()] = (str(pdf_path), page_no, dpi)


def _log_call(h, model, detail, prompt, images, hit):
    if not CALL_LOG:
        return
    imgs = []
    for im in images:
        k = hashlib.sha256(im).hexdigest()
        f, pg, dpi = _png_src.get(k, ("", None, None))
        imgs.append({"png_sha256": k, "pdf": os.path.relpath(f, Path(__file__).parent / "data").replace("\\", "/") if f else "",
                     "page": pg, "dpi": dpi})
    with open(CALL_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"cache_key": h, "model": model, "detail": detail, "prompt": prompt, "images": imgs,
                             "cache_hit": hit}, ensure_ascii=False) + "\n")


def page_png(pdf_path, page_no, dpi=200):
    """page_no: 1-based. Rendered PNGs are cached in png_cache/ (keyed on PDF path, size and mtime)."""
    st = Path(pdf_path).stat()
    h = hashlib.sha256(f"{Path(pdf_path).resolve()}|{st.st_size}|{st.st_mtime_ns}|{page_no}|{dpi}".encode()).hexdigest()[:24]
    cf = PNG_CACHE / f"{h}.png"
    if cf.exists():
        png = cf.read_bytes()
        _note_png(png, pdf_path, page_no, dpi)
        return png
    png = _doc(pdf_path)[page_no - 1].get_pixmap(dpi=dpi).tobytes("png")
    cf.write_bytes(png)
    _note_png(png, pdf_path, page_no, dpi)
    return png


TEXT_CACHE = CACHE_ROOT / "text_cache"
TEXT_CACHE.mkdir(parents=True, exist_ok=True)
_texts = {}


def _all_texts(pdf_path, engine):
    """Cache the text of every page of a PDF as JSON in text_cache/ (keyed on file path, size and mtime)."""
    pdf_path = str(pdf_path)
    k = (pdf_path, engine)
    if k in _texts:
        return _texts[k]
    st = Path(pdf_path).stat()
    h = hashlib.sha256(f"{Path(pdf_path).resolve()}|{st.st_size}|{st.st_mtime_ns}|{engine}".encode()).hexdigest()[:24]
    cf = TEXT_CACHE / f"{Path(pdf_path).stem[:40]}_{engine}_{h}.json"
    if cf.exists():
        _texts[k] = json.loads(cf.read_text(encoding="utf-8"))
        return _texts[k]
    if engine == "plumber":
        import logging
        import pdfplumber
        logging.disable(logging.WARNING)
        with pdfplumber.open(pdf_path) as pdf:
            pages = [(pg.extract_text() or "") for pg in pdf.pages]
    else:
        with fitz.open(pdf_path) as doc:
            pages = [pg.get_text() for pg in doc]
    cf.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    _texts[k] = pages
    return pages


def page_text(pdf_path, page_no, engine="plumber"):
    """engine: 'plumber' (reliable title detection) or 'fitz' (the only one that detects titles in some editions).
    page_no is 1-based."""
    return _all_texts(pdf_path, engine)[page_no - 1]


def n_pages(pdf_path):
    return len(_doc(pdf_path))


def ask(prompt, images=(), model=MODEL, detail="high"):
    """images: list of PNG bytes. Returns the parsed JSON object."""
    h = hashlib.sha256((model + detail + prompt).encode() + b"".join(images)).hexdigest()[:24]
    cf = CACHE / f"{h}.json"
    _log_call(h, model, detail, prompt, images, cf.exists())
    if cf.exists():
        return json.loads(cf.read_text(encoding="utf-8"))
    if os.environ.get("SCOURT_CACHE_ONLY"):
        raise RuntimeError(f"cache miss {h} (SCOURT_CACHE_ONLY set; no API call made)")
    content = [{"type": "text", "text": prompt}]
    for im in images:
        content.append({"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(im).decode(), "detail": detail}})
    r = client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_object"},
    )
    out = json.loads(r.choices[0].message.content)
    cf.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
