"""Turn one original file into committed text: text files as they are, documents converted to Markdown.

Originals are never committed (docs/decisions/0002-committed-extracted-sources.md). Converters come from the
ingest app's Nix closure: pdftotext (poppler), pandoc, python-pptx and openpyxl.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".rst", ".adoc", ".org", ".tex", ".bib", ".csv", ".tsv", ".json", ".jsonl", ".yaml",
    ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml", ".sql", ".graphql", ".proto", ".nix", ".sh", ".bash", ".zsh",
    ".ps1", ".bat", ".cmd", ".py", ".ipynb", ".r", ".jl", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue",
    ".svelte", ".css", ".scss", ".java", ".kt", ".kts", ".scala", ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".cs", ".fs", ".swift", ".m", ".mm", ".rb", ".php", ".pl", ".lua", ".dart", ".ex", ".exs", ".erl", ".hs", ".clj",
    ".elm", ".zig", ".tf", ".hcl", ".cmake", ".gradle", ".properties", ".env.example", ".dockerfile",
}
TEXT_NAMES = {"dockerfile", "makefile", "justfile", "license", "readme", "changelog", "contributing", "codeowners"}
PANDOC_SUFFIXES = {".docx": "docx", ".odt": "odt", ".epub": "epub", ".rtf": "rtf", ".html": "html", ".htm": "html"}
SKIPPED_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "cargo.lock", "flake.lock", "poetry.lock", "uv.lock",
    "composer.lock", "gemfile.lock", "go.sum",
}


class Skip(Exception):
    """The file is not ingested; the message is the reason recorded in the manifest."""


def stored_name(original: str, converted: bool) -> str:
    """Where the text of an original lands: Markdown stays .md, everything else gets a suffix, so no
    ingested file can act on Git, Nix or the tools (.gitignore, .gitattributes, flake.nix). Characters outside
    [A-Za-z0-9._/-] become '_', so every stored path can be cited as [sources/...] without quoting."""
    safe = re.sub(r"[^A-Za-z0-9._/-]", "_", original)
    if not converted and safe.lower().endswith(".md"):
        return safe
    return f"{safe}.md" if converted else f"{safe}.txt"


def is_text_name(name: str) -> bool:
    lower = Path(name).name.lower()
    suffix = Path(lower).suffix
    return suffix in TEXT_SUFFIXES or lower in TEXT_NAMES or Path(lower).stem in TEXT_NAMES


def decode(data: bytes) -> str:
    if b"\0" in data[:8192]:
        raise Skip("binary content")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def run_tool(argv: list[str], data: bytes, suffix: str) -> str:
    if shutil.which(argv[0]) is None:
        raise Skip(f"{argv[0]} is not available; run through ./rc ingest so the Nix closure provides it")
    with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
        handle.write(data)
        handle.flush()
        result = subprocess.run([*argv, handle.name] if argv[0] == "pandoc" else [*argv, handle.name, "-"],
                                capture_output=True, timeout=300)
    if result.returncode != 0:
        raise Skip(f"{argv[0]} failed: {result.stderr.decode(errors='replace').strip()[:200]}")
    return result.stdout.decode("utf-8", errors="replace")


def pptx_text(data: bytes) -> str:
    from pptx import Presentation  # provided by the ingest app

    deck = Presentation(io.BytesIO(data))
    parts = []
    for number, slide in enumerate(deck.slides, 1):
        texts = [shape.text_frame.text.strip() for shape in slide.shapes if shape.has_text_frame and shape.text_frame.text.strip()]
        notes = slide.notes_slide.notes_text_frame.text.strip() if slide.has_notes_slide else ""
        parts.append(f"## Slide {number}\n\n" + "\n\n".join(texts) + (f"\n\nNotes: {notes}" if notes else ""))
    return "\n\n".join(parts)


def xlsx_text(data: bytes, max_rows: int = 200) -> str:
    from openpyxl import load_workbook  # provided by the ingest app

    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    for sheet in book.worksheets:
        rows = []
        for index, row in enumerate(sheet.iter_rows(values_only=True)):
            if index >= max_rows:
                rows.append(f"(first {max_rows} rows only)")
                break
            rows.append(" | ".join("" if cell is None else str(cell) for cell in row))
        parts.append(f"## Sheet {sheet.title}\n\n" + "\n".join(rows))
    return "\n\n".join(parts)


def extract(name: str, data: bytes) -> tuple[str, str, str]:
    """(text, stored name, extractor) for one original file, or Skip."""
    lower = Path(name).name.lower()
    suffix = Path(lower).suffix
    if lower in SKIPPED_NAMES or lower.endswith((".min.js", ".min.css", ".map")):
        raise Skip("generated or lock file")
    if suffix == ".pdf":
        return run_tool(["pdftotext", "-layout", "-enc", "UTF-8"], data, ".pdf"), stored_name(name, True), "pdftotext"
    if suffix in PANDOC_SUFFIXES:
        text = run_tool(["pandoc", "--from", PANDOC_SUFFIXES[suffix], "--to", "gfm-raw_html", "--wrap", "none"], data, suffix)
        return text, stored_name(name, True), "pandoc"
    if suffix == ".pptx":
        return pptx_text(data), stored_name(name, True), "python-pptx"
    if suffix == ".xlsx":
        return xlsx_text(data), stored_name(name, True), "openpyxl"
    if is_text_name(name):
        return decode(data), stored_name(name, False), "text"
    raise Skip(f"unsupported file type {suffix or lower}")


def html_to_markdown(data: bytes) -> str:
    return run_tool(["pandoc", "--from", "html", "--to", "gfm-raw_html", "--wrap", "none"], data, ".html")
