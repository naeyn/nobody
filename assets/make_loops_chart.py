#!/usr/bin/env python3
"""Generate the complete seven-loop research comparison in light/dark SVG.

Loops 2-3 used the original German canonical set. Loops 4-7 use protocol v2.
They are drawn in separate visual families because their absolute measurements
are not directly comparable. Loop 1 produced no frozen canonical finalist.
Sources and methodology: RESEARCH.md.

Usage: python3 assets/make_loops_chart.py
"""

from pathlib import Path
from xml.sax.saxutils import escape

W, H = 1200, 820
BODY = "ui-sans-serif, system-ui, -apple-system, &quot;Segoe UI&quot;, sans-serif"
DISPLAY = "Georgia, &quot;Times New Roman&quot;, serif"
MONO = "ui-monospace, &quot;SFMono-Regular&quot;, Menlo, Consolas, monospace"

LIGHT = {
    "bg": "#f7f9f8", "panel": "#ffffff", "text": "#122017", "muted": "#56645b",
    "faint": "#849087", "line": "#dce3de", "grid": "#e8ede9", "green": "#087f4f",
    "green_soft": "#dcefe6", "pink": "#d84f86", "pink_soft": "#f9e1eb",
    "blue": "#2879c7", "blue_soft": "#e2eef9", "amber": "#b87400",
    "passband": "#edf7f1", "shadow": "rgba(18,32,23,0.08)", "suffix": "light",
}
DARK = {
    "bg": "#121714", "panel": "#1a211d", "text": "#f5f8f6", "muted": "#bac5be",
    "faint": "#7f8d84", "line": "#354039", "grid": "#29332d", "green": "#3fc58a",
    "green_soft": "#183b2b", "pink": "#e26798", "pink_soft": "#442332",
    "blue": "#5da1e3", "blue_soft": "#1d354c", "amber": "#e5a63d",
    "passband": "#172b21", "shadow": "rgba(0,0,0,0.30)", "suffix": "dark",
}

# Loop, headline, experiment, result, status family.
LOOPS = [
    (1, "Build the instrument", "Evaluator, leakage metric, bounded synthetic runs", "No frozen canonical finalist", "blue"),
    (2, "First gated line", "Target-shaped synthetic data + deterministic replay", "0.662 F1  ·  1.74% leak¹", "blue"),
    (3, "Break the address blocker", "Full epochs, OpenPII mix, WiSE-FT", "0.783 F1  ·  2.67% leak¹  ·  G2 fail", "blue"),
    (4, "Protocol v2", "Larger gate, licensed 38,581-instance mix", "v0.2.0  ·  0.791 F1  ·  1.63% leak", "green"),
    (5, "Hunt residual leaks", "Building numbers, dates, phone collision guards", "0.799 F1  ·  2.05% leak  ·  G2 fail", "pink"),
    (6, "Try training and ensembles", "Component addresses, routing, voting", "best F1 0.815  ·  2.61% leak  ·  G2 fail", "pink"),
    (7, "Fix calibration first", "DEV-2 exposes DOB + phone blind spots", "v0.3.0  ·  0.795 F1  ·  1.51% leak", "green"),
]

# label, leakage %, F1, family, short secondary label
POINTS = [
    ("Loop 2 release line", 1.74, 0.662, "blue", "legacy protocol"),
    ("Loop 3 research finalist", 2.67, 0.783, "blue", "legacy protocol · G2 fail"),
    ("v0.2.0 · loop 4", 1.63, 0.791, "green", "first public release"),
    ("Loop 5 finalist", 2.05, 0.799, "pink", "G2 fail by 0.049pp"),
    ("Loop 6 single model", 2.05, 0.801, "pink", "G2 fail"),
    ("Loop 6 ensemble", 2.61, 0.815, "pink", "highest F1 · G2 fail"),
    ("v0.3.0 · loop 7", 1.51, 0.795, "green", "current release · all gates pass"),
]
PIIRANHA = ("Piiranha", 0.93, 0.840, "comparison only · CC-BY-NC-ND")

# Protocol-v2 trajectory omits legacy-protocol loops 2-3.
TRACE = ["v0.2.0 · loop 4", "Loop 5 finalist", "Loop 6 single model", "v0.3.0 · loop 7"]
CLASSES = [
    ("Address", 15.85, 15.55),
    ("Date of birth", 2.71, 0.45),
    ("Phone number", 1.49, 0.69),
    ("Person", 0.62, 0.62),
]

# Layout.
TX0, TX1 = 38, 470
PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 500, 91, 662, 534
PX0, PX1, PY0, PY1 = 565, 1118, 180, 520
LEAK_MIN, LEAK_MAX = 0.6, 2.9
F1_MIN, F1_MAX = 0.64, 0.852
GATE = 2.0


def txt(x, y, value, size, fill, weight=400, anchor="start", family=BODY, letter=0):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
        f'letter-spacing="{letter}">{escape(value)}</text>'
    )


def line(x1, y1, x2, y2, stroke, width=1, dash=None, opacity=1):
    attrs = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"{attrs}/>')


def sx(leak):
    return PX0 + (leak - LEAK_MIN) / (LEAK_MAX - LEAK_MIN) * (PX1 - PX0)


def sy(f1):
    return PY1 - (f1 - F1_MIN) / (F1_MAX - F1_MIN) * (PY1 - PY0)


def build(c):
    o = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'role="img" aria-label="Complete comparison of seven nobody PII research loops, including every '
        'measured finalist, v0.2.0, v0.3.0, and Piiranha">',
        f'<rect width="{W}" height="{H}" fill="{c["bg"]}"/>',
        txt(38, 47, "Seven loops. Two releases. One leakage budget.", 25, c["text"], 600, family=DISPLAY),
        txt(38, 72, "A complete record: frozen finalists, failed gates, and the current comparison.", 12.5, c["muted"]),
    ]

    # Left: seven-loop lab notebook. No text is clipped or ellipsized.
    o.append(txt(TX0, 111, "LAB NOTEBOOK / 01—07", 10.5, c["faint"], 700, letter=1.2))
    row_y, row_h = 132, 75
    for idx, (num, title, work, result, family) in enumerate(LOOPS):
        y = row_y + idx * row_h
        colour = c[family]
        soft = c[f"{family}_soft"]
        if idx < len(LOOPS)-1:
            o.append(line(TX0+16, y+33, TX0+16, y+row_h+2, c["line"], 1.5))
        o.append(f'<circle cx="{TX0+16}" cy="{y+18}" r="15" fill="{soft}" stroke="{colour}" stroke-width="1.2"/>')
        o.append(txt(TX0+16, y+22, f"{num:02d}", 9.5, colour, 750, "middle", MONO))
        o.append(txt(TX0+44, y+12, title, 12.2, c["text"], 700))
        o.append(txt(TX0+44, y+31, work, 10.6, c["muted"]))
        o.append(txt(TX0+44, y+51, result, 10.6, colour, 650, family=MONO))
    o.append(txt(TX0+44, 675, "¹ Original canonical protocol; not directly comparable to v2.", 9.6, c["faint"]))

    # Right panel shell.
    o.append(f'<rect x="{PANEL_X}" y="{PANEL_Y}" width="{PANEL_W}" height="{PANEL_H}" rx="12" '
             f'fill="{c["panel"]}" stroke="{c["line"]}"/>')
    o.append(txt(PANEL_X+24, PANEL_Y+31, "ALL MEASURED FINALISTS", 10.5, c["faint"], 750, letter=1.1))
    o.append(txt(PANEL_X+24, PANEL_Y+53, "Exact-span F1 vs PII token leakage", 14, c["text"], 700))

    # Plot passband and grid.
    o.append(f'<rect x="{PX0}" y="{PY0}" width="{sx(GATE)-PX0:.1f}" height="{PY1-PY0}" fill="{c["passband"]}"/>')
    for f1 in (0.65, 0.70, 0.75, 0.80, 0.85):
        y = sy(f1)
        o.append(line(PX0, y, PX1, y, c["grid"]))
        o.append(txt(PX0-12, y+4, f"{f1:.2f}", 10, c["faint"], 400, "end", MONO))
    for leak in (1.0, 1.5, 2.0, 2.5):
        x = sx(leak)
        o.append(line(x, PY0, x, PY1, c["grid"]))
        o.append(txt(x, PY1+20, f"{leak:.1f}%", 10, c["faint"], 400, "middle", MONO))
    gate_x = sx(GATE)
    o.append(line(gate_x, PY0, gate_x, PY1, c["amber"], 1.5, "5 4"))
    o.append(txt(gate_x-8, PY0-10, "2.00% RELEASE GATE", 9.5, c["amber"], 750, "end", MONO, 0.5))
    o.append(txt(PX0+8, PY0-10, "← SHIPPABLE LEAKAGE", 9.5, c["green"], 750, family=MONO, letter=0.5))
    o.append(txt(PX0-12, PY0-10, "F1", 10, c["muted"], 700, "end", MONO))
    o.append(txt((PX0+PX1)/2, PY1+41, "PII TOKEN LEAKAGE  ·  LOWER IS BETTER", 9.5, c["faint"], 700, "middle", MONO, 0.5))

    # Legacy trace, protocol-v2 trace, and loop-6 ensemble branch.
    by_name = {p[0]: p for p in POINTS}
    legacy = [by_name["Loop 2 release line"], by_name["Loop 3 research finalist"]]
    o.append(f'<path d="M{sx(legacy[0][1]):.1f} {sy(legacy[0][2]):.1f} L{sx(legacy[1][1]):.1f} {sy(legacy[1][2]):.1f}" '
             f'fill="none" stroke="{c["blue"]}" stroke-width="1.4" stroke-dasharray="2 5" opacity="0.65"/>')
    trace_path = " ".join(
        f"{'M' if i == 0 else 'L'}{sx(by_name[name][1]):.1f} {sy(by_name[name][2]):.1f}"
        for i, name in enumerate(TRACE)
    )
    o.append(f'<path d="{trace_path}" fill="none" stroke="{c["muted"]}" stroke-width="1.6" '
             'stroke-dasharray="4 4" opacity="0.72"/>')
    o.append(line(sx(2.05), sy(0.801), sx(2.61), sy(0.815), c["pink"], 1.2, "2 4", 0.65))

    # Piiranha comparator, with full label.
    pname, pl, pf, pnote = PIIRANHA
    px, py = sx(pl), sy(pf)
    o.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="7" fill="{c["panel"]}" stroke="{c["blue"]}" '
             'stroke-width="2" stroke-dasharray="3 2"/>')
    o.append(line(px+7, py, px+22, py, c["blue"], 1))
    o.append(txt(px+27, py-3, "Piiranha  ·  0.840 F1 / 0.93%", 10.5, c["blue"], 700, family=MONO))
    o.append(txt(px+27, py+13, pnote, 9.2, c["faint"]))

    # Point labels. Explicit placements avoid overlap; every point has a leader.
    labels = {
        "Loop 2 release line": (sx(1.74)-12, sy(0.662)-22, "end"),
        "Loop 3 research finalist": (sx(2.67)-14, sy(0.783)+31, "end"),
        "v0.2.0 · loop 4": (sx(1.63)-17, sy(0.791)-27, "end"),
        "Loop 5 finalist": (sx(2.05)-17, sy(0.799)+43, "end"),
        "Loop 6 single model": (sx(2.05)+19, sy(0.801)-26, "start"),
        "Loop 6 ensemble": (sx(2.61)-17, sy(0.815)-28, "end"),
        "v0.3.0 · loop 7": (sx(1.51)-18, sy(0.795)+25, "end"),
    }
    for label, leak, f1, family, note in POINTS:
        x, y, colour = sx(leak), sy(f1), c[family]
        lx, ly, anchor = labels[label]
        ex = lx + (7 if anchor == "start" else -7)
        o.append(line(x, y, ex, ly-4, colour, 1, opacity=0.65))
        if label == "v0.3.0 · loop 7":
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13" fill="{c["green_soft"]}"/>')
        fill = c["panel"] if family == "blue" else colour
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{fill}" stroke="{colour}" stroke-width="2"/>')
        concise = {
            "Loop 2 release line": "L2 · 0.662 / 1.74% · legacy",
            "Loop 3 research finalist": "L3 · 0.783 / 2.67% · legacy",
            "v0.2.0 · loop 4": "v0.2.0 · 0.791 / 1.63%",
            "Loop 5 finalist": "L5 · 0.799 / 2.05% · fail",
            "Loop 6 single model": "L6 single · 0.801 / 2.05% · fail",
            "Loop 6 ensemble": "L6 ensemble · 0.815 / 2.61% · fail",
            "v0.3.0 · loop 7": "v0.3.0 · 0.795 / 1.51% · pass",
        }[label]
        o.append(txt(lx, ly, concise, 9.8, colour, 750, anchor, MONO))

    # Legend inside plot bottom.
    leg_y = PANEL_Y + PANEL_H - 23
    o.append(f'<circle cx="{PANEL_X+28}" cy="{leg_y}" r="5" fill="{c["panel"]}" stroke="{c["blue"]}" stroke-width="2"/>')
    o.append(txt(PANEL_X+40, leg_y+4, "legacy protocol", 9.4, c["muted"]))
    o.append(f'<circle cx="{PANEL_X+160}" cy="{leg_y}" r="5" fill="{c["green"]}"/>')
    o.append(txt(PANEL_X+172, leg_y+4, "release / gate pass", 9.4, c["muted"]))
    o.append(f'<circle cx="{PANEL_X+310}" cy="{leg_y}" r="5" fill="{c["pink"]}"/>')
    o.append(txt(PANEL_X+322, leg_y+4, "frozen gate failure", 9.4, c["muted"]))

    # Bottom evidence strip: loop 7 mechanism.
    strip_y = 716
    o.append(line(38, 697, W-38, 697, c["line"]))
    o.append(txt(38, strip_y, "LOOP 7 / WHAT MOVED", 9.8, c["faint"], 750, family=MONO, letter=1))
    x = 218
    for label, before, after in CLASSES:
        o.append(txt(x, strip_y, label.upper(), 8.8, c["muted"], 700, family=MONO, letter=0.4))
        o.append(txt(x, strip_y+19, f"{before:.2f}% → {after:.2f}%", 11.2, c["green"], 700, family=MONO))
        x += 172
    o.append(txt(38, 774, "METHOD", 9.8, c["faint"], 750, family=MONO, letter=1))
    o.append(txt(106, 774, "development-only selection  ·  one frozen canonical look per loop  ·  fixed thresholds  ·  contamination checks", 10.2, c["muted"]))
    o.append(txt(106, 794, "paired document bootstrap, 10,000 resamples  ·  all benchmark records synthetic  ·  no raw records published", 10.2, c["faint"]))
    o.append("</svg>")
    return "\n".join(o)


def main():
    output = Path(__file__).resolve().parent
    for theme in (LIGHT, DARK):
        path = output / f"loops-{theme['suffix']}.svg"
        path.write_text(build(theme), encoding="utf-8")
        print("wrote", path)


if __name__ == "__main__":
    main()
