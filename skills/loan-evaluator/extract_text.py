"""Turn a loan document into plain text.

A .docx is a zip archive; the Read tool cannot open it and neither can naive
text I/O. We route each extension to the right library so the tool doesn't
lose the tables (which is where DSCR, LTV and equity figures actually live).
"""
from __future__ import annotations

import sys
from pathlib import Path


SUPPORTED = (".docx", ".pdf", ".md", ".txt", "")


def _docx_to_text(path: Path) -> str:
    # Import lazily so a user scoring a .md file never needs python-docx.
    from docx import Document
    from docx.document import Document as _Doc
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table, _Cell
    from docx.text.paragraph import Paragraph

    ROW_SEP = " | "  # so a row still reads as one line after joining

    def iter_block_items(parent):
        # Walk paragraphs AND tables in document order — losing order or the
        # tables would drop the financial summary entirely.
        if isinstance(parent, _Doc):
            parent_elm = parent.element.body
        elif isinstance(parent, _Cell):
            parent_elm = parent._tc
        else:
            raise ValueError("unsupported parent")
        for child in parent_elm.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)

    def render(container) -> list[str]:
        out: list[str] = []
        for block in iter_block_items(container):
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if text:
                    out.append(text)
            else:  # Table — recurse into cells for nested tables
                for row in block.rows:
                    cells: list[str] = []
                    for cell in row.cells:
                        inner = " ".join(render(cell))
                        cells.append(inner.strip())
                    out.append(ROW_SEP.join(cells))
        return out

    return "\n".join(render(Document(str(path))))


def _pdf_to_text(path: Path) -> str:
    from pdfminer.high_level import extract_text as pdf_extract
    return pdf_extract(str(path))


def _plain_to_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Loan document not found: {p}")
    suffix = p.suffix.lower()
    if suffix == ".docx":
        return _docx_to_text(p)
    if suffix == ".pdf":
        return _pdf_to_text(p)
    if suffix in (".md", ".txt", ""):
        return _plain_to_text(p)
    raise ValueError(
        f"Unsupported file type '{suffix}'. Supported: {', '.join(s or '<none>' for s in SUPPORTED)}"
    )


def _main(argv: list[str]) -> int:
    # Windows consoles default to cp1252 and will crash on real loan docs.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    if len(argv) != 2:
        print("usage: python extract_text.py <file>", file=sys.stderr)
        return 2
    print(extract(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
