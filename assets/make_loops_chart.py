#!/usr/bin/env python3
"""Generate the seven-loop research chart in light and dark themes.

The chart contains only measured results. Loops 2-3 used the original German
canonical set; loops 4-7 use protocol v2, so only loops 4-7 share the lower
quantitative plot. Sources and methodology are documented in RESEARCH.md.

Usage: python3 assets/make_loops_chart.py
"""

from pathlib import Path
from xml.sax.saxutils import escape

FONT = "system-ui, -apple-system, &quot;Segoe UI&quot;, sans-serif"
W, H = 1080, 760

LIGHT = {
    "bg": "#fcfcfb", "frame": "rgba(11,11,11,0.10)", "text": "#0b0b0b",
    "muted": "#52514e", "faint": "#898781", "grid": "rgba(11,11,11,0.08)",
    "ship": "#008300", "fail": "#e87ba4", "ref": "#2a78d6",
    "card": "#f4f4f1", "passband": "rgba(0,131,0,0.055)", "suffix": "light",
}
DARK = {
    "bg": "#1a1a19", "frame": "rgba(255,255,255,0.12)", "text": "#ffffff",
    "muted": "#c3c2b7", "faint": "#898781", "grid": "rgba(255,255,255,0.10)",
    "ship": "#00a300", "fail": "#d55181", "ref": "#3987e5",
    "card": "#242422", "passband": "rgba(0,163,0,0.09)", "suffix": "dark",
}

# label, title, measurement, work, outcome, colour family
LOOPS = [
    ("1", "Instrument", "bounded runs", "evaluator + synthetic baseline", "no release", "ref"),
    ("2", "Synthetic", "0.662 F1 · 1.74%", "targeted data + replay", "first gate pass¹", "ref"),
    ("3", "Data mix", "0.783 F1 · 2.67%", "OpenPII + WiSE-FT", "G2 failed¹", "ref"),
    ("4", "Protocol v2", "0.791 F1 · 1.63%", "mix38k checkpoint", "v0.2.0 shipped", "ship"),
    ("5", "Leak hunt", "0.799 F1 · 2.05%", "address / phone / DOB", "G2 failed", "fail"),
    ("6", "Ensembles", "0.815 F1 · 2.61%", "routing + data waves", "G2 failed", "fail"),
    ("7", "Calibration", "0.795 F1 · 1.51%", "DEV-2 exposed blind spots", "v0.3.0 ships", "ship"),
]

# Protocol-v2 plot: label, leakage %, F1, colour family.
POINTS = [
    ("v0.2.0", 1.63, 0.791, "ship"),
    ("loop 5", 2.05, 0.799, "fail"),
    ("loop 6", 2.05, 0.801, "fail"),
    ("loop 6 ensemble", 2.61, 0.815, "fail"),
    ("v0.3.0", 1.51, 0.795, "ship"),
]
TRAJECTORY = ["v0.2.0", "loop 5", "loop 6", "v0.3.0"]
PIIRANHA = (0.93, 0.840)
CLASSES = [
    ("address", 15.85, 15.55),
    ("date of birth", 2.71, 0.45),
    ("phone number", 1.49, 0.69),
    ("person", 0.62, 0.62),
]

PX0, PX1, PY0, PY1 = 86, 640, 300, 614
LEAK_MIN, LEAK_MAX = 0.6, 2.85
F1_MIN, F1_MAX = 0.780, 0.852
GATE = 2.0
BX0, BX1, BY0 = 735, 1036, 350


def text(x, y, value, size, fill, weight=400, anchor="start"):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def sx(leak):
    return PX0 + (leak - LEAK_MIN) / (LEAK_MAX - LEAK_MIN) * (PX1 - PX0)


def sy(f1):
    return PY1 - (f1 - F1_MIN) / (F1_MAX - F1_MIN) * (PY1 - PY0)


def build(c):
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'role="img" aria-label="Seven research loops improving the nobody German PII redaction pipeline, '
        'ending with v0.3.0 at 0.795 F1 and 1.51 percent PII token leakage">',
        f'<rect width="{W}" height="{H}" fill="{c["bg"]}" rx="8"/>',
        f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" fill="none" stroke="{c["frame"]}" rx="8"/>',
        text(32, 42, "Seven loops from baseline to a shippable leakage budget", 19, c["text"], 650),
        text(32, 65, "Every finalist was selected on development data before one frozen canonical evaluation.", 12.5, c["muted"]),
    ]

    # Seven-loop timeline.
    card_y, card_w, card_h, gap = 96, 137, 122, 10
    for i, (num, title, metric, work, outcome, family) in enumerate(LOOPS):
        x = 32 + i * (card_w + gap)
        colour = c[family]
        if i:
            out.append(f'<path d="M{x-gap+2} {card_y+61} L{x-3} {card_y+61}" stroke="{c["faint"]}" '
                       'stroke-width="1.2"/>')
            out.append(f'<path d="M{x-7} {card_y+57} L{x-3} {card_y+61} L{x-7} {card_y+65}" '
                       f'fill="none" stroke="{c["faint"]}" stroke-width="1.2"/>')
        out.append(f'<rect x="{x}" y="{card_y}" width="{card_w}" height="{card_h}" rx="7" '
                   f'fill="{c["card"]}" stroke="{c["grid"]}"/>')
        out.append(f'<circle cx="{x+18}" cy="{card_y+20}" r="11" fill="{colour}" opacity="0.16"/>')
        out.append(text(x+18, card_y+24, num, 11, colour, 700, "middle"))
        out.append(text(x+36, card_y+24, title, 11.5, c["text"], 650))
        out.append(text(x+10, card_y+51, metric, 10.5, colour, 650))
        out.append(text(x+10, card_y+72, work, 9.6, c["muted"]))
        out.append(text(x+10, card_y+92, outcome, 10.2, colour, 600))

    out.append(text(32, 239, "¹ Loops 2–3 used the original canonical set; protocol v2 begins at loop 4.", 10.5, c["faint"]))

    # Lower plot title.
    out.append(text(PX0, 276, "Protocol-v2 trajectory", 13.5, c["text"], 650))
    out.append(text(PX0+174, 276, "same model weights; pipeline changes only", 10.5, c["faint"]))

    # Pass region, gate, and grid.
    out.append(f'<rect x="{PX0}" y="{PY0}" width="{sx(GATE)-PX0:.1f}" height="{PY1-PY0}" '
               f'fill="{c["passband"]}"/>')
    out.append(f'<line x1="{sx(GATE):.1f}" y1="{PY0}" x2="{sx(GATE):.1f}" y2="{PY1}" '
               f'stroke="{c["fail"]}" stroke-width="1.4" stroke-dasharray="5 4"/>')
    out.append(text(sx(GATE)-8, PY0-9, "2.0% gate", 11, c["fail"], 650, "end"))
    out.append(text(PX0+7, PY0-9, "← shippable leakage", 11, c["ship"], 600))
    for f1 in (0.78, 0.79, 0.80, 0.81, 0.82, 0.83, 0.84, 0.85):
        y = sy(f1)
        out.append(f'<line x1="{PX0}" y1="{y:.1f}" x2="{PX1}" y2="{y:.1f}" stroke="{c["grid"]}"/>')
        out.append(text(PX0-10, y+4, f"{f1:.2f}", 10.5, c["faint"], 400, "end"))
    for leak in (1.0, 1.5, 2.0, 2.5):
        out.append(text(sx(leak), PY1+19, f"{leak:.1f}%", 10.5, c["faint"], 400, "middle"))
    out.append(text(PX0-10, PY0-23, "F1", 11, c["muted"], 600, "end"))
    out.append(text((PX0+PX1)/2, PY1+39, "PII token leakage (lower is better)", 11, c["muted"], 400, "middle"))

    by_label = {point[0]: point for point in POINTS}
    path = " ".join(
        f"{'M' if i == 0 else 'L'}{sx(by_label[label][1]):.1f} {sy(by_label[label][2]):.1f}"
        for i, label in enumerate(TRAJECTORY)
    )
    out.append(f'<path d="{path}" fill="none" stroke="{c["faint"]}" stroke-width="1.6" '
               'stroke-dasharray="4 3" opacity="0.8"/>')
    out.append(f'<path d="M{sx(2.05):.1f} {sy(0.801):.1f} L{sx(2.61):.1f} {sy(0.815):.1f}" '
               f'fill="none" stroke="{c["fail"]}" stroke-width="1.2" stroke-dasharray="2 3" opacity="0.7"/>')

    # Comparator.
    pl, pf = PIIRANHA
    out.append(f'<circle cx="{sx(pl):.1f}" cy="{sy(pf):.1f}" r="6" fill="none" '
               f'stroke="{c["ref"]}" stroke-width="1.8" stroke-dasharray="3 2"/>')
    out.append(text(sx(pl)+12, sy(pf)-2, "Piiranha 0.840", 11, c["ref"], 650))
    out.append(text(sx(pl)+12, sy(pf)+13, "comparison only · CC-BY-NC-ND", 9.8, c["faint"]))

    # Result points and collision-free labels.
    placements = {
        "v0.2.0": (14, 28, "start"),
        "loop 5": (-12, -10, "end"),
        "loop 6": (12, -7, "start"),
        "loop 6 ensemble": (12, 4, "start"),
        "v0.3.0": (-13, -13, "end"),
    }
    for label, leak, f1, family in POINTS:
        x, y, colour = sx(leak), sy(f1), c[family]
        radius = 7 if label == "v0.3.0" else 5.5
        if label == "v0.3.0":
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="12" fill="{colour}" opacity="0.16"/>')
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{colour}"/>')
        dx, dy, anchor = placements[label]
        weight = 700 if label == "v0.3.0" else 550
        out.append(text(x+dx, y+dy, label, 11.2, colour if label == "v0.3.0" else c["muted"], weight, anchor))

    # Per-class leakage change from loop 6 C1 to v0.3.0.
    out.append(text(BX0, 276, "What loop 7 fixed", 13.5, c["text"], 650))
    out.append(text(BX0, 296, "per-class token leakage: loop 6 → v0.3.0", 10.5, c["faint"]))
    scale = (BX1-BX0) / 16.0
    row = BY0
    for name, before, after in CLASSES:
        out.append(text(BX0, row-7, name, 11, c["muted"], 550))
        out.append(f'<rect x="{BX0}" y="{row}" width="{max(before*scale, 1.8):.1f}" height="7" '
                   f'fill="{c["faint"]}" opacity="0.55" rx="2"/>')
        out.append(f'<rect x="{BX0}" y="{row+11}" width="{max(after*scale, 1.8):.1f}" height="7" '
                   f'fill="{c["ship"]}" rx="2"/>')
        out.append(text(BX0+max(before*scale, 1.8)+6, row+7, f"{before:.2f}%", 9.8, c["faint"]))
        out.append(text(BX0+max(after*scale, 1.8)+6, row+18, f"{after:.2f}%", 9.8, c["ship"], 650))
        row += 46
    out.append(f'<line x1="{BX0}" y1="{row+4}" x2="{BX1}" y2="{row+4}" stroke="{c["grid"]}"/>')
    out.append(text(BX0, row+28, "total 2.05% → 1.51%", 12.5, c["text"], 650))
    out.append(text(BX0, row+47, "95% CI: 1.08–1.995%", 10.5, c["faint"]))
    out.append(text(BX0, row+63, "first strict leakage-gate pass", 10.5, c["ship"], 650))

    # Method footer.
    out.append(f'<line x1="32" y1="690" x2="{W-32}" y2="690" stroke="{c["grid"]}"/>')
    out.append(text(32, 714, "One frozen canonical look per loop · fixed production thresholds · development-only selection · contamination checks", 11.2, c["muted"]))
    out.append(text(32, 733, "Document-level paired bootstrap (10,000 resamples) · all benchmark documents are synthetic · no real personal records are published", 11.2, c["faint"]))
    out.append("</svg>")
    return "\n".join(out)


def main():
    output = Path(__file__).resolve().parent
    for theme in (LIGHT, DARK):
        path = output / f"loops-{theme['suffix']}.svg"
        path.write_text(build(theme), encoding="utf-8")
        print("wrote", path)


if __name__ == "__main__":
    main()
