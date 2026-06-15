"""Generate data/PROJECT_REPORT.pdf — a project/design report.

Pure standard library (no third-party deps), so it never clashes with other
installs. Uses the built-in Courier core font (monospace) so line wrapping is
exact without needing font-metric tables.
"""
from __future__ import annotations

import textwrap
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data" / "PROJECT_REPORT.pdf"

PAGE_W, PAGE_H = 612, 792           # US Letter, points
MARGIN = 54                         # 0.75"
LEFT = MARGIN
TOP = PAGE_H - MARGIN
BOTTOM = MARGIN
USABLE_W = PAGE_W - 2 * MARGIN      # 504 pt
CHAR_W = 0.6                        # Courier advance = 0.6 em

# Font sizes / leading per block style
STYLE = {
    "title": (18, "F2", 24, 10),    # (size, font, leading, space_after)
    "h1":    (14, "F2", 20, 8),
    "h2":    (11, "F2", 16, 5),
    "body":  (10, "F1", 13.5, 7),
    "bullet":(10, "F1", 13.5, 2),
    "rule":  (0,  "F1", 8, 0),
}

# Transliterate non-ASCII so WinAnsi/Courier always renders cleanly.
TRANS = {
    "…": "...", "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "→": "->", "×": "x", "‰": "per mille",
    "‑": "-", " ": " ", "•": "-", "é": "e", "≤": "<=",
}


def _ascii(s: str) -> str:
    for k, v in TRANS.items():
        s = s.replace(k, v)
    return s.encode("ascii", "replace").decode("ascii")


def _esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def cpl(size: float) -> int:
    return max(8, int(USABLE_W / (CHAR_W * size)))


def parse(md: str):
    """Tiny Markdown subset -> list of (style, text) blocks."""
    blocks = []
    for raw in md.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            blocks.append(("space", ""))
        elif line.strip() == "---":
            blocks.append(("rule", ""))
        elif line.startswith("# "):
            blocks.append(("title", line[2:]))
        elif line.startswith("## "):
            blocks.append(("h1", line[3:]))
        elif line.startswith("### "):
            blocks.append(("h2", line[4:]))
        elif line.startswith("- "):
            blocks.append(("bullet", line[2:]))
        else:
            blocks.append(("body", line))
    return blocks


def layout(blocks):
    """Flow blocks into pages -> list of pages, each a list of draw ops."""
    pages, ops, y = [], [], TOP

    def newpage():
        nonlocal ops, y
        if ops:
            pages.append(ops)
        ops, y = [], TOP

    for style, text in blocks:
        if style == "space":
            y -= 7
            continue
        if style == "rule":
            if y - 8 < BOTTOM:
                newpage()
            ops.append(("rule", LEFT, y - 4, PAGE_W - MARGIN))
            y -= 8
            continue
        size, font, leading, after = STYLE[style]
        prefix = "  -  " if style == "bullet" else ""
        indent_w = len(prefix)
        wrapped = textwrap.wrap(_ascii(text), width=cpl(size) - indent_w) or [""]
        for i, ln in enumerate(wrapped):
            if y - leading < BOTTOM:
                newpage()
            shown = (prefix if i == 0 else " " * indent_w) + ln
            ops.append(("text", font, size, LEFT, y - leading + 3, _esc(shown)))
            y -= leading
        y -= after
    newpage()
    return pages


def build_pdf(pages) -> bytes:
    objs: list[bytes] = []

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)

    # Reserve catalog(1) + pages(2); fonts 3,4
    add(b"")  # 1 catalog (filled later)
    add(b"")  # 2 pages   (filled later)
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold /Encoding /WinAnsiEncoding >>")

    page_ids = []
    for ops in pages:
        parts = []
        for op in ops:
            if op[0] == "text":
                _, font, size, x, y, s = op
                parts.append(
                    f"BT /{font} {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({s}) Tj ET")
            elif op[0] == "rule":
                _, x0, y0, x1 = op
                parts.append(f"{x0:.2f} {y0:.2f} m {x1:.2f} {y0:.2f} l 0.6 w S")
        stream = "\n".join(parts).encode("latin-1")
        comp = zlib.compress(stream)
        cid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comp)
                  + comp + b"\nendstream")
        pid = add(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> "
            b"/Contents %d 0 R >>" % (PAGE_W, PAGE_H, f1, f2, cid))
        page_ids.append(pid)

    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objs[1] = (f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>").encode()
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"

    # Serialize with xref
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs)+1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF").encode()
    return bytes(out)


def main():
    md = (Path(__file__).resolve().parent / "data" / "PROJECT_REPORT.md").read_text(encoding="utf-8")
    pages = layout(parse(md))
    OUT.write_bytes(build_pdf(pages))
    words = len(md.split())
    print(f"Wrote {OUT}  ({len(pages)} pages, ~{words} words)")


if __name__ == "__main__":
    main()
