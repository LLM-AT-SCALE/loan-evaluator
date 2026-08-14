"""Deterministic credit scorecard engine + PDF writer.

The point of this file is that the DECISION is arithmetic, not judgement:
the analyst reads and scores 1-5; this file weights, sums, and looks up a band.
No AI, no network, no API key.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUBRIC_PATH = HERE / "rubric.json"
OUTPUT_DIR = HERE / "output"


# --------------------------------------------------------------------------- #
# Scoring                                                                     #
# --------------------------------------------------------------------------- #

def _load_rubric() -> dict:
    return json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))


def score_application(ratings_doc: dict, rubric: dict) -> dict:
    """Weight the 1-5 scores, look up the decision band, then apply hard rules."""
    by_id = {r["id"]: r for r in ratings_doc.get("ratings", [])}
    lines: list[dict] = []
    flags: list[str] = []
    total = 0.0

    for r in rubric["rubrics"]:
        rid, name, weight = r["id"], r["name"], r["weight"]
        rating = by_id.get(rid)
        score = rating.get("score") if rating else None

        if score is None or score == "N/E":
            display = "N/E"
            points = 0.0
            flags.append(f"{rid} ({name}): scored N/E — no evidence in the narrative.")
        else:
            display = int(score)
            points = (display / 5.0) * weight
            total += points

        lines.append({
            "id": rid,
            "name": name,
            "weight": weight,
            "score": display,
            "points": round(points, 2),
            "evidence": (rating or {}).get("evidence", ""),
            "note": (rating or {}).get("note", ""),
        })

    total = round(total, 1)

    # Band lookup first, then apply hard rules that can override.
    decision, note = "DECLINE", ""
    for band in rubric["decision_bands"]:
        if band["min"] <= total <= band["max"]:
            decision, note = band["decision"], band["note"]
            break

    hard_rule_triggered = None
    c2 = by_id.get("C2", {}).get("score")
    if c2 == 1:
        hard_rule_triggered = next(
            (h for h in rubric.get("hard_rules", []) if h["id"] == "HR-1"), None
        )
        if hard_rule_triggered:
            decision = hard_rule_triggered["action"]
            note = hard_rule_triggered["reason"]
            flags.append(f"HARD RULE {hard_rule_triggered['id']} triggered: {hard_rule_triggered['reason']}")

    return {
        "lines": lines,
        "total": total,
        "decision": decision,
        "decision_note": note,
        "flags": flags,
        "hard_rule": hard_rule_triggered,
    }


# --------------------------------------------------------------------------- #
# PDF                                                                         #
# --------------------------------------------------------------------------- #

_DECISION_COLOURS = {
    "APPROVE": ("#1b7a3a", "#e3f4e8"),                    # green
    "APPROVE WITH CONDITIONS": ("#8a5a00", "#fff2d6"),    # amber
    "REFER TO CREDIT COMMITTEE": ("#b3541a", "#ffe3d0"),  # orange
    "DECLINE": ("#8b1a1a", "#fcd9d9"),                    # red
}


def _sanitise(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name or "borrower").strip("_")
    return slug or "borrower"


def write_pdf(ratings_doc: dict, result: dict, path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title", parent=styles["Title"], fontSize=18, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=9.5, leading=12)
    small = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=8, textColor=colors.grey, leading=10)
    quote = ParagraphStyle(
        "Quote", parent=body, fontName="Helvetica-Oblique",
        leftIndent=14, textColor=colors.HexColor("#333333"),
        spaceBefore=2, spaceAfter=2,
    )
    decision_style = ParagraphStyle(
        "Decision", parent=styles["Heading1"], fontSize=16,
        alignment=1, spaceBefore=4, spaceAfter=2,
    )
    decision_note_style = ParagraphStyle(
        "DecisionNote", parent=body, alignment=1, fontSize=9, textColor=colors.HexColor("#333333"),
    )

    story = []

    # 1. Header
    story.append(Paragraph("CREDIT SCORECARD", title))
    hdr = [
        ["Borrower:", ratings_doc.get("borrower", ""), "Application #:", ratings_doc.get("application_no", "")],
        ["Loan Amount:", ratings_doc.get("loan_amount", ""), "Date Scored:", date.today().isoformat()],
    ]
    hdr_tbl = Table(hdr, colWidths=[1.05 * inch, 2.7 * inch, 1.05 * inch, 2.4 * inch])
    hdr_tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9.5),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9.5),
        ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 10))

    # 2. Decision banner
    fg, bg = _DECISION_COLOURS.get(result["decision"], ("#333333", "#eeeeee"))
    banner = Table(
        [[Paragraph(f'<font color="{fg}">{result["decision"]}</font>', decision_style)],
         [Paragraph(f'<b>{result["total"]:.1f} / 100</b>', decision_style)],
         [Paragraph(result["decision_note"], decision_note_style)]],
        colWidths=[7.2 * inch],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(fg)),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(banner)
    story.append(Spacer(1, 10))

    # 3. Score table
    rows = [["#", "Rubric", "Score", "Weight", "Points"]]
    for ln in result["lines"]:
        score_txt = "N/E" if ln["score"] == "N/E" else f'{ln["score"]}/5'
        rows.append([ln["id"], ln["name"], score_txt, str(ln["weight"]), f'{ln["points"]:.1f}'])
    rows.append(["", "TOTAL", "", "100", f'{result["total"]:.1f}'])
    tbl = Table(rows, colWidths=[0.5 * inch, 2.6 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch])
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecf1")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#888888")),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9.5),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f4f4f4")),
        ("FONT", (0, 1), (-1, -2), "Helvetica", 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 10))

    # 4. Evidence
    story.append(Paragraph("Evidence and reasoning", h2))
    for ln in result["lines"]:
        score_txt = "N/E" if ln["score"] == "N/E" else f'{ln["score"]}/5'
        story.append(Paragraph(f'<b>{ln["id"]} — {ln["name"]} ({score_txt})</b>', body))
        if ln["evidence"]:
            story.append(Paragraph(ln["evidence"], quote))
        else:
            story.append(Paragraph("<i>No evidence recorded in the narrative.</i>", quote))
        if ln["note"]:
            story.append(Paragraph(ln["note"], body))
        story.append(Spacer(1, 4))

    # 5. Conditions to address — the WEAKEST raw 1-5 score(s), not fewest points.
    scored = [ln for ln in result["lines"] if ln["score"] != "N/E"]
    story.append(Paragraph("Conditions to address", h2))
    if not scored:
        story.append(Paragraph("Every rubric was N/E — no scored evidence to weight.", body))
    else:
        lowest = min(ln["score"] for ln in scored)
        if lowest == 5:
            story.append(Paragraph("Every rubric scored the maximum. No conditions recommended.", body))
        else:
            weakest = [ln for ln in scored if ln["score"] == lowest]
            for ln in weakest:
                story.append(Paragraph(
                    f'<b>{ln["id"]} — {ln["name"]} (score {ln["score"]}/5).</b> '
                    f'Weakest rubric. A covenant should address this: {ln["note"] or "see evidence above."}',
                    body,
                ))
                story.append(Spacer(1, 2))

    # 6. Flags
    if result["flags"]:
        story.append(Paragraph("Flags", h2))
        for f in result["flags"]:
            story.append(Paragraph(f"• {f}", body))

    # 7. Footer
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Scores 1–5 are the analyst's reading of the narrative. The decision is "
        "arithmetic from rubric.json: re-running with the same scores always "
        "produces the same decision. Any N/E rubric flags missing evidence for a human to chase.",
        small,
    ))

    doc = SimpleDocTemplate(
        str(path), pagesize=LETTER,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        title="Credit Scorecard",
    )
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Self-test                                                                   #
# --------------------------------------------------------------------------- #

def _self_test() -> int:
    rubric = _load_rubric()

    # Reference case: 4,4,4,4,3 → 16 + 24 + 16 + 16 + 6 = 78.0 → APPROVE WITH CONDITIONS.
    ref = {"ratings": [
        {"id": "C1", "score": 4},
        {"id": "C2", "score": 4},
        {"id": "C3", "score": 4},
        {"id": "C4", "score": 4},
        {"id": "C5", "score": 3},
    ]}
    res = score_application(ref, rubric)
    assert res["total"] == 78.0, f"reference total was {res['total']}, expected 78.0"
    assert res["decision"] == "APPROVE WITH CONDITIONS", f"reference decision was {res['decision']}"

    # Hard rule: C2=1 overrides an otherwise perfect application.
    hr = {"ratings": [
        {"id": "C1", "score": 5},
        {"id": "C2", "score": 1},
        {"id": "C3", "score": 5},
        {"id": "C4", "score": 5},
        {"id": "C5", "score": 5},
    ]}
    res2 = score_application(hr, rubric)
    assert res2["decision"] == "DECLINE", f"hard-rule decision was {res2['decision']}"

    print("SELF-TEST PASSED")
    return 0


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def _main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Score a commercial loan application.")
    parser.add_argument("ratings", nargs="?", help="Path to ratings.json")
    parser.add_argument("--self-test", action="store_true", help="Run internal correctness check.")
    # Shipped as a skill, this file lives in a plugin cache directory that is
    # replaced on every update. The scorecard must land in the user's own
    # working directory instead, so -o is how the caller redirects it.
    parser.add_argument("-o", "--out", help="Directory or full path for the PDF "
                                            "(default: ./output beside this file)")
    args = parser.parse_args(argv[1:])

    if args.self_test:
        return _self_test()

    if not args.ratings:
        parser.error("ratings.json path required (or use --self-test)")

    ratings_doc = json.loads(Path(args.ratings).read_text(encoding="utf-8"))
    rubric = _load_rubric()
    result = score_application(ratings_doc, rubric)

    pdf_name = f"{_sanitise(ratings_doc.get('borrower', 'borrower'))}_scorecard.pdf"
    if args.out:
        target = Path(args.out)
        # A path ending in .pdf is a filename; anything else is a directory.
        dest = target if target.suffix.lower() == ".pdf" else target / pdf_name
    else:
        dest = OUTPUT_DIR / pdf_name
    pdf_path = write_pdf(ratings_doc, result, dest)

    print(f"{result['decision']} — {result['total']:.1f}/100 — {pdf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
