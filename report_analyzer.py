from __future__ import annotations

import io
import os
import re
from typing import Any
import xml.etree.ElementTree as ET
import requests

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import streamlit as st
except ImportError:
    st = None


GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"


def _get_groq_api_key() -> str:
    """Reads GROQ_API_KEY from environment variables or Streamlit secrets."""
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key and st is not None:
        try:
            key = str(st.secrets.get("GROQ_API_KEY", "")).strip()
        except Exception:
            key = ""
    return key


def extract_pdf_pages(pdf_bytes: bytes, max_pages: int = 80) -> list[dict[str, Any]]:
    """Extracts clean text per page from PDF bytes with 1-indexed page numbers."""
    if PdfReader is None:
        raise RuntimeError("pypdf is not installed. Run: pip install pypdf")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages: list[dict[str, Any]] = []
    for idx, page in enumerate(reader.pages[:max_pages], start=1):
        raw_text = page.extract_text() or ""
        cleaned = re.sub(r"\s+", " ", raw_text).strip()
        if cleaned:
            pages.append({"page": idx, "text": cleaned})
    return pages


def extract_xbrl_xml_pages(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Parses raw NSE XBRL .xml bytes into human-readable tag/value lines."""
    root = ET.fromstring(xml_bytes)
    lines: list[str] = []
    for elem in root.iter():
        text = (elem.text or "").strip()
        if text and not text.startswith("http"):
            tag = elem.tag.split("}")[-1]
            readable_tag = re.sub(r"([a-z])([A-Z])", r"\1 \2", tag)
            lines.append(f"{readable_tag}: {text}")

    joined = "\n".join(lines)
    return [{"page": 1, "text": joined[:25000]}] if joined else []


def retrieve_relevant_chunks(
    pages: list[dict[str, Any]],
    query: str,
    top_k: int = 6,
    chunk_size: int = 1200,
) -> list[dict[str, Any]]:
    """Ranks extracted document page chunks by lexical and financial metric overlap."""
    chunks: list[dict[str, Any]] = []
    for p in pages:
        txt = p["text"]
        pg = p["page"]
        for start in range(0, len(txt), chunk_size - 200):
            piece = txt[start : start + chunk_size].strip()
            if len(piece) > 80:
                chunks.append({"page": pg, "text": piece})

    if not chunks:
        return []

    q_terms = {
        w.lower()
        for w in re.findall(r"[a-zA-Z0-9%₹\.]+", query)
        if len(w) > 2
    }
    finance_boost_terms = {
        "revenue", "ebitda", "pat", "profit", "margin", "guidance",
        "capex", "debt", "growth", "yoy", "qoq", "crore", "dividend",
        "risk", "outlook", "segment", "order", "book",
    }

    scored: list[tuple[float, dict[str, Any]]] = []
    for ch in chunks:
        lower = ch["text"].lower()
        q_hits = sum(2.0 for t in q_terms if t in lower)
        fin_hits = sum(0.5 for f in finance_boost_terms if f in lower)
        num_density = min(len(re.findall(r"\d+(?:\.\d+)?%?", ch["text"])) * 0.1, 2.5)
        scored.append((q_hits + fin_hits + num_density, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:top_k]]


def analyze_report_with_grounding(
    pages: list[dict[str, Any]],
    doc_name: str,
    question: str = "Extract key financial results, YoY/QoQ growth, margins, management guidance, and key risks.",
    groq_model: str = DEFAULT_GROQ_MODEL,
) -> dict[str, Any]:
    """Generates strictly factual, [Page X]-cited insights from retrieved PDF or XBRL chunks."""
    top_chunks = retrieve_relevant_chunks(pages, query=question, top_k=6)
    if not top_chunks:
        return {
            "answer": "No readable text found in this filing (it may be a scanned image without OCR text).",
            "citations": [],
            "mode": "Empty Text",
        }

    context_blocks = "\n\n".join(
        [f"[Page {c['page']}]: {c['text']}" for c in top_chunks]
    )

    system_rules = (
        "You are Dalal Lens's Factual Financial Document Analyst. "
        "Answer the user's question using ONLY the provided filing excerpts below. "
        "STRICT RULES:\n"
        "1. Cite every factual claim or number inline using [Page X].\n"
        "2. Do NOT invent, estimate, or extrapolate any figures not explicitly stated in the text.\n"
        "3. Structure the response clearly with bullet points under: "
        "**Key Factual Highlights**, **Financial & Operational Metrics**, and **Risks / Caveats**.\n"
        "4. If the document does not mention something asked by the user, explicitly state: "
        "'Not mentioned in the provided report excerpts.'"
    )

    user_prompt = (
        f"Document: {doc_name}\n"
        f"User Question: {question}\n\n"
        f"--- VERIFIED FILING EXCERPTS ---\n{context_blocks}\n"
        f"--- END EXCERPTS ---\n\n"
        f"Factual Grounded Response:"
    )

    groq_key = _get_groq_api_key()
    if groq_key:
        try:
            resp = requests.post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": groq_model,
                    "messages": [
                        {"role": "system", "content": system_rules},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 1200,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                choices = resp.json().get("choices", [])
                if choices:
                    answer_text = choices[0]["message"]["content"].strip()
                    if answer_text:
                        return {
                            "answer": answer_text,
                            "citations": top_chunks,
                            "mode": f"Groq ({groq_model}, temp=0.0)",
                        }
        except Exception:
            pass

    try:
        ollama_resp = requests.post(
            OLLAMA_URL,
            json={
                "model": DEFAULT_OLLAMA_MODEL,
                "prompt": f"{system_rules}\n\n{user_prompt}",
                "stream": False,
                "options": {"temperature": 0.0, "num_ctx": 8192},
            },
            timeout=20,
        )
        if ollama_resp.status_code == 200:
            answer_text = ollama_resp.json().get("response", "").strip()
            if answer_text:
                return {
                    "answer": answer_text,
                    "citations": top_chunks,
                    "mode": f"Local Ollama ({DEFAULT_OLLAMA_MODEL}, temp=0.0)",
                }
    except Exception:
        pass

    fallback_bullets = "\n".join(
        [f"- **[Page {c['page']}]:** {c['text'][:420]}..." for c in top_chunks[:4]]
    )
    return {
        "answer": (
            f"*(Set `GROQ_API_KEY` for full AI synthesis — showing top grounded excerpts for `{doc_name}`)*\n\n"
            f"{fallback_bullets}"
        ),
        "citations": top_chunks,
        "mode": "Extractive Grounding Fallback (No GROQ_API_KEY)",
    }


def analyze_pdf_report(
    pdf_url: str,
    question: str = "Extract key financial results, YoY/QoQ growth, margins, management guidance, and key risks.",
) -> dict[str, Any]:
    """Downloads PDF or XBRL (.xml) bytes from URL, extracts pages, and runs grounded analysis."""
    try:
        resp = requests.get(
            pdf_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://www.nseindia.com/",
            },
            timeout=15,
        )
        resp.raise_for_status()
        if pdf_url.lower().split("?")[0].endswith(".xml"):
            pages = extract_xbrl_xml_pages(resp.content)
        else:
            pages = extract_pdf_pages(resp.content)
        doc_name = pdf_url.split("/")[-1] or "Report.pdf"
        return analyze_report_with_grounding(pages=pages, doc_name=doc_name, question=question)
    except Exception as e:
        return {
            "answer": f"Error downloading or analyzing filing from URL: {e}",
            "citations": [],
            "mode": "Error",
        }