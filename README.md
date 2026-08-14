# Loan Evaluator

A Claude Code skill that scores a commercial loan application narrative against
the five C's of credit and produces a PDF credit scorecard.

**The analyst reads. The code decides.** Claude scores each of five rubrics 1–5
and quotes the sentence justifying every score. The approve/decline decision
comes from `score_loan.py`, which weights those scores and looks up a band — so
the same scores always produce the same decision, and anyone can audit it.

## Install

```
/plugin marketplace add <account>/loan-evaluator
/plugin install loan-evaluator
```

## Use

```
/loan-evaluator harbor-point.docx
```

Accepts `.docx`, `.pdf`, `.md`, `.txt`. Invoke with no file and it will ask for
a path. Say `sample` to score the bundled sample application.

Output:

```
APPROVE WITH CONDITIONS — 78.0/100
./Harbor_Point_Fabrication_LLC_scorecard.pdf
```

The PDF lands in your current working directory.

## Requirements

- Claude Code
- Python 3.10+

Python packages (`reportlab`, `python-docx`, `pdfminer.six`) are installed
automatically on first run. **No API key. No server. No hosting.** Everything
runs locally using your existing Claude login.

## The rubric

Five rubrics, weighted, from `rubric.json`:

| ID | Rubric | Weight | Hard metric |
|---|---|---|---|
| C1 | Character | 20 | — |
| C2 | Capacity | 30 | DSCR |
| C3 | Capital | 20 | Equity injection % |
| C4 | Collateral | 20 | LTV |
| C5 | Conditions | 10 | — |

Decision bands: **85–100** approve · **70–84** approve with conditions ·
**55–69** refer to credit committee · **0–54** decline.

One hard rule: a Capacity score of 1 (DSCR below 1.00x) forces a decline
regardless of the weighted total. Hard rules are applied *after* the band
lookup — reverse that order and a loan that cannot cover its own debt service
gets silently upgraded to a pass.

## Changing the criteria

Edit `skills/loan-evaluator/rubric.json` — weights, level descriptors and
decision bands all live there. Push, and users pick it up with:

```
/plugin update loan-evaluator
```

Verify any change to the engine with:

```
python skills/loan-evaluator/score_loan.py --self-test
```
