"""Generate data/PROJECT_REPORT.pdf from data/PROJECT_REPORT.md.

Pure standard library (no third-party deps). Uses the built-in Courier core
font so line wrapping and table alignment are exact without font-metric tables.
Supports a small Markdown subset plus fenced ``` blocks rendered verbatim
(monospace) for ASCII diagrams and aligned tables.

The audit table (SQL table -> manual table -> ASSAR page) is injected where the
report contains the {{AUDIT_TABLE}} placeholder, so the mapping lives in one
authoritative place here.

    python make_report.py
"""
from __future__ import annotations

import textwrap
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "PROJECT_REPORT.pdf"
MD = ROOT / "data" / "PROJECT_REPORT.md"

PAGE_W, PAGE_H = 612, 792
MARGIN = 54
LEFT = MARGIN
TOP = PAGE_H - MARGIN
BOTTOM = MARGIN
USABLE_W = PAGE_W - 2 * MARGIN
CHAR_W = 0.6

STYLE = {
    "title":  (18, "F2", 24, 10),
    "h1":     (14, "F2", 20, 8),
    "h2":     (11, "F2", 16, 5),
    "body":   (10, "F1", 13.5, 7),
    "bullet": (10, "F1", 13.5, 2),
    "pre":    (8.5, "F1", 11, 1),   # verbatim blocks (diagrams, tables)
    "rule":   (0, "F1", 8, 0),
}

TRANS = {
    "…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-",
    "→": "->", "×": "x", "‰": "per mille", "‑": "-", "•": "-", "é": "e", "≤": "<=",
}


def _ascii(s: str) -> str:
    for k, v in TRANS.items():
        s = s.replace(k, v)
    return s.encode("ascii", "replace").decode("ascii")


def _esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def cpl(size: float) -> int:
    return max(8, int(USABLE_W / (CHAR_W * size)))


# --------------------------------------------------------------------------- #
# Audit mapping: SQL table -> manual table / source -> ASSAR page(s)
# Ordered by page so it reads as a walk through the manual; derived/metadata
# tables (no single source table) are grouped at the end.
# --------------------------------------------------------------------------- #
AUDIT = [
    ("voluntary_deductible_discount", "Schedule of Approved Discounts for Voluntary Deductible", "p.13"),
    ("special_perils", "Special Perils and Respective Perils Premium Rate", "p.15"),
    ("short_period_scale", "Scale of Rates for Short Period Insurance", "p.16"),
    ("fire_allied_perils", "Fire and Allied Perils Insurance - Commercial/Administrative (Material Damage)", "p.19-22"),
    ("fire_private_dwellings", "Fire Private Dwellings (All Perils Inclusive)", "p.22"),
    ("plate_glass", "Pricing of Plate Glass Insurance", "p.22"),
    ("consequential_loss_basis", "Rating for Consequential Loss - basis items (Gross Profit / Auditors Fees / Wages)", "p.24"),
    ("consequential_loss_indemnity_period", "Indemnity Period Selected - Percentages of the Basis Rate", "p.24"),
    ("business_interruption_time_excess", "Voluntary Time Excess under Business Interruption", "p.24"),
    ("burglary_full_value", "Burglary & Theft - Full Value Basis minimum rates", "p.28"),
    ("first_loss_multiplier", "Risks Insured on First Loss Basis - multipliers", "p.28"),
    ("bankers_blanket_bond", "Bankers Blanket Bond - Description of Risk / Rate", "p.31"),
    ("directors_officers_liability", "Directors and Officers Liability - Description of Risk / Rate", "p.32"),
    ("money_insurance", "Money and Cash in Transit - rates (in safe, ATM, out of safe, custody)", "p.33-34"),
    ("money_annual_carryings", "Money in Transit - Annual Carryings rate bands", "p.33"),
    ("goods_in_transit", "Goods in Transit - commodity rate grid", "p.36-38"),
    ("transporters_liability", "Transporters Liability - commodity rate grid", "p.42-44"),
    ("public_liability", "Public Liability - Minimum Premium Rate", "p.46"),
    ("employers_liability", "Employers' Liability - Minimum Premium Rate", "p.47"),
    ("school_liability", "School Liability - premiums and indemnity limits", "p.47-48"),
    ("school_liability_short_period", "Short Rates for School Liability", "p.48"),
    ("product_liability", "Product Liability - Minimum Premium Rate", "p.49"),
    ("professional_indemnity", "Professional Indemnity - Professional Classification / Rate", "p.50"),
    ("personal_accident_gpa", "PA & GPA Risks Categories and Minimum Premium / Rates", "p.51"),
    ("personal_accident_short_period", "Short Rates for Personal and Group Personal Accident", "p.52"),
    ("erection_all_risks", "Erection All Risks (EAR) - Minimum Rate", "p.53-54"),
    ("machinery_breakdown", "Machinery Breakdown - Minimum Rates", "p.55-56"),
    ("cpm_rates", "Contractors Plant & Machinery (CPM) - Hazard Class x Plant Group", "p.57"),
    ("cpm_short_period", "Short Period Rates under CPM", "p.57-58"),
    ("boilers_pressure_vessels", "Boilers and Pressure Vessels - Material Damage / TPL", "p.58"),
    ("eear_computer_all_risks", "Computer and Electric & Electronic All Risks (EEAR)", "p.58-59"),
    ("contractors_all_risks", "Contractors' All Risks - Minimum Rate", "p.62-63"),
    ("aviation", "Pricing of Aviation Risks - Description of Risk / Applicable Rate", "p.64"),
    ("marine_hull", "Rates for Vessels / Marine Hull rating procedure", "p.66"),
    ("marine_hull_occupant_premiums", "Premiums and Sums Insured for 1 Occupant (Bodily Injuries)", "p.66"),
    ("marine_cargo", "Rates for Marine Cargo (ICC-A)", "p.67-69"),
    ("bonds_guarantees", "Pricing of Bonds/Guarantees - Description of Bond / Rate", "p.70"),
    ("fidelity_guarantee", "Pricing of Fidelity Guarantee - Description of Risk / Rate", "p.71"),
    ("pvt_political_violence_terrorism", "Pricing of PVT Risks - Description of Risk / per-mille rate", "p.72-73"),
    ("large_risks_property", "List of Large Risks Established in the Market - Property", "p.76-79"),
    ("large_risks_engineering", "List of Large Risks - Engineering", "p.80"),
    ("large_risks_accident", "List of Large Risks - Accident Classes", "p.80"),
    ("market_parameters", "Derived: policy fee (p.12), FEA discount (p.16), stock declaration (p.29), commission (p.75)", "p.12-75"),
    ("minimum_premiums", "Derived: minimum premiums across classes (money p.34, liabilities p.46-49, PA/GPA p.52, bonds p.71, fidelity p.72)", "multiple"),
    ("data_dictionary", "Engine metadata - documents the unit of every column (not a manual table)", "n/a"),
]


def build_audit_block() -> str:
    c1, c2 = 33, 11
    mw = 92 - c1 - c2 - 2
    lines = ["```"]
    lines.append(f"{'SQL TABLE':<{c1}} {'PAGE(S)':<{c2}} MANUAL TABLE / SOURCE")
    lines.append(f"{'-' * c1} {'-' * c2} {'-' * mw}")
    for sql, manual, page in AUDIT:
        wrapped = textwrap.wrap(manual, mw) or [""]
        lines.append(f"{sql:<{c1}} {page:<{c2}} {wrapped[0]}")
        for cont in wrapped[1:]:
            lines.append(f"{'':<{c1}} {'':<{c2}} {cont}")
    lines.append(f"\nTotal: {len(AUDIT)} tables.")
    lines.append("```")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Markdown subset -> blocks -> pages -> PDF
# --------------------------------------------------------------------------- #
def parse(md: str):
    blocks, in_pre = [], False
    for raw in md.split("\n"):
        if raw.strip().startswith("```"):
            in_pre = not in_pre
            continue
        if in_pre:
            blocks.append(("pre", raw))
            continue
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
        if style == "pre":
            if y - leading < BOTTOM:
                newpage()
            shown = _ascii(text)[:cpl(size)]
            ops.append(("text", font, size, LEFT, y - leading + 3, _esc(shown)))
            y -= leading
            continue
        prefix = "  -  " if style == "bullet" else ""
        indent = len(prefix)
        for i, ln in enumerate(textwrap.wrap(_ascii(text), width=cpl(size) - indent) or [""]):
            if y - leading < BOTTOM:
                newpage()
            shown = (prefix if i == 0 else " " * indent) + ln
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

    add(b"")  # 1 catalog
    add(b"")  # 2 pages
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold /Encoding /WinAnsiEncoding >>")

    page_ids = []
    for ops in pages:
        parts = []
        for op in ops:
            if op[0] == "text":
                _, font, size, x, y, s = op
                parts.append(f"BT /{font} {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({s}) Tj ET")
            elif op[0] == "rule":
                _, x0, y0, x1 = op
                parts.append(f"{x0:.2f} {y0:.2f} m {x1:.2f} {y0:.2f} l 0.6 w S")
        comp = zlib.compress("\n".join(parts).encode("latin-1"))
        cid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comp) + comp + b"\nendstream")
        pid = add(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
            % (PAGE_W, PAGE_H, f1, f2, cid))
        page_ids.append(pid)

    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objs[1] = (f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>").encode()
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs)+1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF").encode()
    return bytes(out)


def main():
    md = MD.read_text(encoding="utf-8").replace("{{AUDIT_TABLE}}", build_audit_block())
    pages = layout(parse(md))
    OUT.write_bytes(build_pdf(pages))
    print(f"Wrote {OUT}  ({len(pages)} pages, {len(AUDIT)} audited tables, ~{len(md.split())} words)")


if __name__ == "__main__":
    main()
