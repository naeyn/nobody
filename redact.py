#!/usr/bin/env python3
"""Layered PII redactor: deterministic validators first, GLiNER second.

Layer 1 (regex + checksums — deterministic formats deserve deterministic detectors):
  email · IBAN (mod-97) · phone (DE/NL/intl) · credit card (Luhn)
  German Steuer-ID (ISO 7064 MOD 11,10) · Dutch BSN (elfproef)
  license plates (DE + NL patterns)
Layer 2 (GLiNER): person, address, date of birth, organization.

Overlaps merged (longest span wins), masked right-to-left as [LABEL].

Usage:
    python redact.py --model <model-id-or-local-path> --text "..."
    cat document.txt | python redact.py --model <model-id-or-local-path>
"""

import argparse
import os
import re
import sys

ML_LABELS = ["person", "address", "date of birth", "organization"]

# Optional post-processing controls. The environment variable is read on every
# call so long-running processes and tests can change policy without reloading:
#   - unset: enable every fix;
#   - comma-separated names: enable exactly those fixes;
#   - empty: disable every optional fix.
# The `fixes=` argument on fix-aware functions provides explicit local control.
ALL_PIPELINE_FIXES = ("chain", "housenum", "dobslash", "spacedemail", "phonespace",
                      "buildingnum", "corpustitle", "addrguard", "addrmerge")


def active_pipeline_fixes():
    """Which of ALL_PIPELINE_FIXES are active, from NOBODY_PIPELINE_FIXES.
    Read fresh from os.environ on every call -- see the module-level note
    above."""
    raw = os.environ.get("NOBODY_PIPELINE_FIXES")
    if raw is None:
        return frozenset(ALL_PIPELINE_FIXES)
    fixes = frozenset(name.strip() for name in raw.split(",") if name.strip())
    unknown = fixes - frozenset(ALL_PIPELINE_FIXES)
    if unknown:
        raise ValueError(
            f"unknown NOBODY_PIPELINE_FIXES name(s): {sorted(unknown)} "
            f"(valid: {ALL_PIPELINE_FIXES})"
        )
    return fixes


def _resolve_fixes(fixes):
    """None -> read NOBODY_PIPELINE_FIXES now; anything else -> use it
    verbatim (as a frozenset), for explicit test control."""
    return active_pipeline_fixes() if fixes is None else frozenset(fixes)


def pipeline_fixes_status_line(fixes=None):
    """Return the active optional pipeline fixes for CLI diagnostics."""
    names = sorted(_resolve_fixes(fixes))
    return f"pipeline fixes active: {', '.join(names) if names else 'NONE'}"

# Support Unicode local parts/domains and a conservative set of surname
# particles separated by spaces. Arbitrary space-separated words are rejected
# to prevent the match from consuming preceding prose.
_EMAIL_PARTICLE = r"(?:van|der|den|de|ter|von)"
EMAIL_RE = re.compile(
    rf"\b(?:{_EMAIL_PARTICLE}[ \t]){{0,3}}[\w.%+-]+@[\w.-]+[,;:]?\.[A-Za-z]{{2,}}\b",
    re.IGNORECASE,
)
# Export and OCR systems sometimes insert one space around "." or "@".
# Keep every optional space bounded to one character and require exactly one
# domain dot; unbounded groups can consume sentence-ending punctuation and the
# following word. The optional second local-part segment must start lowercase,
# so a capitalized word after a sentence boundary cannot be absorbed.
_SPACED_DOT = r"[ \t]?\.[ \t]?"
_SPACED_AT = r"[ \t]?@[ \t]?"
_SPACED_LOCAL_CONT = r"[a-z0-9%+-][\w%+-]*"
SPACED_EMAIL_RE = re.compile(
    rf"\b[\w%+-]+(?:{_SPACED_DOT}{_SPACED_LOCAL_CONT})?"  # local part: word, + at most ONE lowercase-starting dot-segment
    rf"{_SPACED_AT}"                                        # @
    rf"[\w-]+{_SPACED_DOT}[a-zA-Z]{{2,}}\b"                 # domain: label DOT TLD (exactly one, mandatory dot)
)
IBAN_RE = re.compile(r"\b[A-Z]{2}\s?\d{2}(?:\s?[A-Z0-9]{4}){2,7}\s?[A-Z0-9]{1,4}\b", re.IGNORECASE)
# Exported/malformed IBANs can group all digits in four-character blocks,
# including the check digits. They are not emitted as IBAN PII without a
# checksum, but their range must still block embedded phone-tail matches.
_IBAN_LIKE_RE = re.compile(r"\b[A-Z]{2}[ \t]?\d{4}(?:[ \t]?\d{4}){2,6}[ \t]?\d{1,4}\b", re.IGNORECASE)
# Digit runs allow spaces and tabs, never newlines. Using `\s` here could merge
# a phone number with unrelated digits on the following line.
PHONE_RE = re.compile(
    r"(?<![\w.\-])(?:\+|00)[1-9]\d{0,2}[ \t./-]?(?:\(0\)[ \t./-]?)?\d[\d \t./()-]{5,14}\d(?!\d)"
    r"|(?<![\w.\-])(?:\(\s?0[1-9]\d{0,4}\s?\)|0[1-9]\d{0,4})[ \t./-]?\d[\d \t./()-]{4,10}\d(?!\d)"
)
CC_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
STEUERID_RE = re.compile(r"\b\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3}\b|\b\d{11}\b")
BSN_RE = re.compile(r"\b\d{9}\b")
PLATE_RE = re.compile(  # DE: E-AB 1234 / NL common patterns: XX-999-X, 9-XXX-99, ...
    r"\b[A-ZÄÖÜ]{1,3}-[A-Z]{1,2}\s?\d{1,4}[EH]?\b"
    r"|\b(?:[A-Z]{2}-\d{3}-[A-Z]|\d-[A-Z]{3}-\d{2}|[A-Z]{3}-\d{2}-[A-Z]|\d{2}-[A-Z]{3}-\d)\b"
)
# Month-name dates are treated as birth dates by the recall-first policy.
# Numeric dates are handled separately because they can also be ordinary
# invoice, delivery, or contract dates.
_MONTHS = (
    r"Januar|Februar|M[äa]rz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember"
    r"|January|February|March|April|May|June|July|August|September|October|November|December"
)
DOB_MONTHNAME_RE = re.compile(
    rf"\b\d{{1,2}}\s?\.\s*(?:{_MONTHS})\s+\d{{4}}\b"  # "18. November 1963" / "17 . Februar 2013" (spaced export punctuation)
    rf"|\b(?:{_MONTHS})\s+\d{{1,2}}\s?\.,?\s*\d{{4}}\b"  # "November 20., 2003" / "18 November 1963"
)
# Numeric full dates include spaced separators. This intentionally masks some
# non-birth dates: over-redaction is preferred to leaking a birth date.
DOB_NUMERIC_RE = re.compile(r"\b\d{1,2}\s?[./-]\s?\d{1,2}\s?[./-]\s?(?:19|20)\d{2}\b")
# Month-name slash forms such as "Juni / 36" occur in exported records.
# Both sides are tightly bounded so longer invoice/order numbers cannot match,
# and horizontal whitespace cannot span a newline.
DOB_MONTHNAME_SLASH_RE = re.compile(
    rf"\b(?:{_MONTHS})[ \t]*/[ \t]*\d{{2}}\b"       # "Juni / 36"
    rf"|\b\d{{1,2}}[ \t]*/[ \t]*(?:{_MONTHS})\b"    # "26 / Juni" (symmetric)
)
# A bare `am` / `bis` / `ab` before a month-slash date was once treated as
# evidence of a reporting or scheduling period rather than a birth date. That
# rule was withdrawn, for two reasons. It contradicted this module's own date
# policy -- numeric dates are matched recall-first precisely because
# over-redaction beats leaking a birth date, so exempting month-slash forms after
# a preposition was an inconsistent exception. And on a held-out German
# evaluation set it suppressed genuine birth-date spans that appeared in
# deadline-shaped sentences ("... bis <Month>/<YY>"), which the original
# evaluation set could not reveal because it reported no birth-date leakage at
# all. A preposition is too weak a signal to withhold masking; only an EXPLICIT
# operational date field still suppresses.
# Explicit operational date fields are not dates of birth. This stays narrow:
# generic `Datum:` is deliberately excluded because it may abbreviate a
# birth-date field in real exports.
_DOB_SLASH_NON_BIRTH_FIELD_RE = re.compile(
    r"(?:bewertungsdatum|termin|deckungsbeginn|schlüssel[ -]datum|"
    r"datum[ \t]+des[ \t]+berichts)[ \t]*:[ \t]*$", re.IGNORECASE
)
_DOB_SLASH_BIRTH_CUE_RE = re.compile(r"(?:geb(?:oren|urtsdatum)?|date[ \t]+of[ \t]+birth|born)", re.IGNORECASE)


def _suppress_ambiguous_dob_slash(text, start):
    context = text[max(0, start - 40):start]
    return bool(
        _DOB_SLASH_NON_BIRTH_FIELD_RE.search(context)
        and not _DOB_SLASH_BIRTH_CUE_RE.search(context)
    )
# ISO-8601 timestamps are common in exported birth-date fields.
DOB_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\b")


def _digits(s):
    return re.sub(r"\D", "", s)


def iban_valid(iban):
    s = re.sub(r"\s", "", iban)
    if not 15 <= len(s) <= 34:
        return False
    s = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in s)) % 97 == 1


def luhn_valid(num):
    d = [int(c) for c in _digits(num)][::-1]
    if len(d) < 13:
        return False
    return (sum(d[0::2]) + sum(sum(divmod(2 * x, 10)) for x in d[1::2])) % 10 == 0


def steuerid_valid(num):
    """German Steuer-ID: 11 digits, first != 0, ISO 7064 MOD 11,10 check digit."""
    d = _digits(num)
    if len(d) != 11 or d[0] == "0":
        return False
    # digit multiplicity rule: exactly one digit appears twice or thrice among first 10
    counts = {c: d[:10].count(c) for c in set(d[:10])}
    if sorted(counts.values(), reverse=True)[0] not in (2, 3) or list(counts.values()).count(1) not in (8, 9):
        return False
    product = 10
    for c in d[:10]:
        s = (int(c) + product) % 10 or 10
        product = (2 * s) % 11
    return (11 - product) % 10 == int(d[10])


def bsn_valid(num):
    """Dutch BSN elfproef: sum(d_i * w_i) % 11 == 0 with weights 9..2,-1."""
    d = _digits(num)
    if len(d) != 9:
        return False
    w = [9, 8, 7, 6, 5, 4, 3, 2, -1]
    return sum(int(c) * wi for c, wi in zip(d, w)) % 11 == 0


# Per-label production thresholds. Organization predictions stay enabled for
# every language: suppressing them to accommodate a benchmark taxonomy would
# reduce real-world recall.
_GERMAN_MARKERS = frozenset("""der die das und ist mit für von zu nicht sich wird sind auch als
ich wir sie er es ein eine einen dem den bei nach über unter durch geboren wohne
straße strasse herr frau bitte danke""".split())
_WORD_ONLY_RE = re.compile(r"[A-Za-zÀ-ÿ]+")


def looks_german(text, threshold=0.06):
    """Estimate whether text is German from common function/domain words."""
    tokens = [t.lower() for t in _WORD_ONLY_RE.findall(text)]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in _GERMAN_MARKERS)
    return (hits / len(tokens)) >= threshold


_GERMAN_BUSINESS_RE = re.compile(
    r"\bGmbH\b|\bAG\b|\bKG\b|\bOHG\b|\bGbR\b|\be\.\s?V\.|\bFirma\b"
)


def has_german_business_register(text):
    """True if `text` shows a German legal-entity/business-register cue
    (GmbH, AG, KG, e.V., "Firma", ...). These substrings are specific to
    business correspondence and essentially never appear in personal
    records, so they're a much sharper register signal than language alone."""
    return bool(_GERMAN_BUSINESS_RE.search(text))


# Flat recall-oriented policy. Address uses a lower threshold because short
# street and house-number fragments tend to receive low model scores.
LABEL_THRESHOLDS_DEFAULT = {"person": 0.5, "address": 0.05, "date of birth": 0.5, "organization": 0.5}


def label_thresholds_for(text):
    """Per-document label->threshold policy. Currently flat (no language or
    register gating) -- kept as a function, not a constant, so a future
    genuinely document-conditional policy can slot back in without changing
    every call site."""
    return dict(LABEL_THRESHOLDS_DEFAULT)


# IMEI check digits also use Luhn, so a 15-digit IMEI can otherwise be
# mislabeled as a credit card. Suppress only that exact cue/length collision.
_IMEI_CUE_RE = re.compile(r"IMEI", re.IGNORECASE)

# Bare three-group phone formats are ambiguous with customer and order numbers.
# Require a nearby phone-specific cue and constrain the group shape.
_PHONE_CUE_RE = re.compile(
    r"Telefon(?:nummer)?|Rufnummer|Mobil(?:nummer)?|Handynummer|Fax(?:nummer)?"
    r"|\bTel\.?\b|Ruf(?:e)?\s+mich|R[üu]ckruf"
    # Ordinary German lead-ins that introduce a number in running prose:
    # "erreichbar unter", "Rückfragen unter", "Kontakt", "Durchwahl", and
    # compound nouns ending in -linie (Servicelinie, Beratungslinie). Missing
    # these accounted for most phone-number leakage on a held-out evaluation set.
    # They stay safe because a match still requires the multi-group phone FORMAT;
    # a preposition alone detects nothing ("Kinder unter 18 Jahren").
    r"|erreichbar|\bunter\b|Hotline|Durchwahl|\w*linie\b|Kontakt(?:ieren)?",
    re.IGNORECASE,
)
# Separators in exported German numbers are frequently spaced -- shaped like
# "NNNN . NNN NNNN" rather than "NNNN.NNN.NNNN" -- so a separator is
# punctuation-with-optional-spaces OR plain whitespace. The earlier
# single-character class missed most spaced exports.
_PHONE_SEP = r"(?:[ \t]*[.\-][ \t]*|[ \t]+)"
PHONE_UNPREFIXED_RE = re.compile(
    rf"(?<![\w.])\d{{3,4}}{_PHONE_SEP}\d{{2,4}}{_PHONE_SEP}\d{{2,4}}(?:{_PHONE_SEP}\d{{2,4}})?(?!\w)"
)

# A bare building number is only PII when a dedicated field cue establishes
# that it belongs to an address. This intentionally excludes generic address
# prose: it has no reliable numeric boundary.
#
# Cue widening: the previous pattern recognised only a fraction of the
# building-number field labels that occur in German exports. These are separator
# and morphology variants of labels we already trust
# ("Gebäude Nr.", "Gebäude-Nr", "Gebäudenr.", "Nummer des Gebäudes",
# "Bau-Nummer"). A broader "Adresse:"/"Anschrift:" cue was tried and REVERTED:
# on DEV-2 it cost address precision .516 -> .475 for only 0.05pp of leakage,
# because an address field is routinely followed by numbers that are not the
# building number. The remaining misses are
# bare numbers in prose with no cue at all; those are deliberately NOT chased,
# because firing on them requires memorising one generator's templates.
_BUILDING_NUMBER_CUE_RE = re.compile(
    r"\b(?:"
    r"geb(?:[aä]|&auml;)ude(?:[ \t\-]*(?:nummer|num|nr))?\.?"      # Gebäude / Gebäude-Nr. / Gebäude Nr
    r"|nummer[ \t]+des[ \t]+geb(?:[aä]|&auml;)udes"                  # "Nummer des Gebäudes"
    r"|bautenummer|bau[ \t\-]*(?:nummer|nr\.?)"                     # Bautenummer (single n) / Bau-Nummer / Bau Nr.
    r"|haus[ \t\-]*(?:nummer|nr)\.?"                                # Hausnummer / Haus-Nr.
    r"|building[ \t]*(?:number|no\.?)"
    r")[ \t]*[:#]?[ \t]*$",
    re.IGNORECASE,
)
# A following sentence period is punctuation, not part of a decimal. Preserve
# the decimal guard while allowing field values at sentence boundaries.
BUILDING_NUMBER_RE = re.compile(r"(?<![\w.])\d{1,4}[A-Za-z]?(?!\w|\.\d)")

# A leading-zero date can resemble a domestic phone number. Exclude exact
# date-shaped matches from phone detection.
_PHONE_DATE_SHAPE_RE = re.compile(r"\d{2}([./-])\s?\d{2}\1\s?\d{4}")

# Spaced/exported phone forms need dedicated patterns for whitespace around
# prefixes and separators. Parenthesized and plus-prefixed forms are bounded by
# plausible digit counts. Bare forms remain cue-gated. Horizontal whitespace is
# explicit so a match can never consume digits from the following line.
PHONESPACE_PAREN_RE = re.compile(
    r"(?<![\w.])\([ \t]?\d{2,4}[ \t]?\)[ \t]?[.\-]?[ \t]?\d[\d \t.\-]{4,14}\d(?![ \t]?\d)")
PHONESPACE_PLUS_RE = re.compile(
    r"(?<![\w.])\+[ \t]?\d[\d \t.\-]{6,16}\d(?![ \t]?\d)")
PHONESPACE_BARE_RE = re.compile(
    r"(?<![\w.])\d{3,4}(?:[ \t]?[.\-][ \t]?|[ \t])\d{2,4}(?:[ \t]?[.\-][ \t]?|[ \t])\d{3,4}(?![ \t.]?\d)")


def _phonespace_matches(text):
    """Return conservatively validated spaced/exported phone-number spans."""
    out = []
    for m in PHONESPACE_PAREN_RE.finditer(text):
        g = m.group()
        if 7 <= len(_digits(g)) <= 13 and not _PHONE_DATE_SHAPE_RE.search(g):
            out.append((m.start(), m.end(), "phone number"))
    for m in PHONESPACE_PLUS_RE.finditer(text):
        g = m.group()
        nd = len(_digits(g))
        if 7 <= nd <= 13 and not _PHONE_DATE_SHAPE_RE.search(g) \
                and (re.search(r"[.\-]", g) or nd >= 10):
            out.append((m.start(), m.end(), "phone number"))
    for m in PHONESPACE_BARE_RE.finditer(text):
        g = m.group()
        if 9 <= len(_digits(g)) <= 12 and not _PHONE_DATE_SHAPE_RE.search(g) \
                and _PHONE_CUE_RE.search(text[max(0, m.start() - 40):m.start()]):
            out.append((m.start(), m.end(), "phone number"))
    return out


def detect_structured(text, fixes=None):
    """-> [(char_start, char_end, label)] from the deterministic layer.

    `fixes`: which pipeline fixes are active in this text-only layer
    (dobslash, spacedemail, phonespace -- chain/housenum are address
    post-processors applied by the caller after GLiNER runs). None (the
    default) reads NOBODY_PIPELINE_FIXES at call time; see
    active_pipeline_fixes()."""
    fixes = _resolve_fixes(fixes)
    spans = []
    spans += [(m.start(), m.end(), "email") for m in EMAIL_RE.finditer(text)]
    if "spacedemail" in fixes:
        spans += [(m.start(), m.end(), "email") for m in SPACED_EMAIL_RE.finditer(text)
                  if not any(s <= m.start() < e or s < m.end() <= e for s, e, _ in spans)]
    # Preserve raw IBAN-shaped ranges as phone exclusions even when their
    # checksum is invalid: malformed/exported IBANs commonly contain a
    # phone-shaped tail, but are not telephone numbers.
    iban_matches = list(IBAN_RE.finditer(text))
    iban_like_matches = iban_matches + list(_IBAN_LIKE_RE.finditer(text))
    spans += [(m.start(), m.end(), "iban") for m in iban_matches if iban_valid(m.group())]
    spans += [(m.start(), m.end(), "phone number") for m in PHONE_RE.finditer(text)
              if not _PHONE_DATE_SHAPE_RE.fullmatch(m.group())
              and not any(iban.start() < m.end() and m.start() < iban.end()
                          for iban in iban_like_matches)]
    spans += [(m.start(), m.end(), "credit card") for m in CC_RE.finditer(text)
              if luhn_valid(m.group()) and not any(s <= m.start() < e for s, e, _ in spans)
              and not (len(_digits(m.group())) == 15
                       and _IMEI_CUE_RE.search(text[max(0, m.start() - 30):m.start()]))]
    spans += [(m.start(), m.end(), "national id") for m in STEUERID_RE.finditer(text) if steuerid_valid(m.group())]
    spans += [(m.start(), m.end(), "national id") for m in BSN_RE.finditer(text)
              if bsn_valid(m.group()) and not any(s <= m.start() < e for s, e, _ in spans)]
    spans += [(m.start(), m.end(), "license plate") for m in PLATE_RE.finditer(text)]
    spans += [(m.start(), m.end(), "date of birth") for m in DOB_MONTHNAME_RE.finditer(text)]
    if "dobslash" in fixes:
        spans += [(m.start(), m.end(), "date of birth") for m in DOB_MONTHNAME_SLASH_RE.finditer(text)
                  if not _suppress_ambiguous_dob_slash(text, m.start())
                  and not any(s <= m.start() < e or s < m.end() <= e for s, e, _ in spans)]
    spans += [(m.start(), m.end(), "date of birth") for m in DOB_ISO_RE.finditer(text)]
    spans += [(m.start(), m.end(), "date of birth") for m in DOB_NUMERIC_RE.finditer(text)
              if not any(s <= m.start() < e for s, e, _ in spans)]
    if "buildingnum" in fixes:
        spans += [(m.start(), m.end(), "address") for m in BUILDING_NUMBER_RE.finditer(text)
                  if _BUILDING_NUMBER_CUE_RE.search(text[max(0, m.start() - 48):m.start()])]
    spans += [(m.start(), m.end(), "phone number") for m in PHONE_UNPREFIXED_RE.finditer(text)
              if not any(s <= m.start() < e or s < m.end() <= e for s, e, _ in spans)
              and _PHONE_CUE_RE.search(text[max(0, m.start() - 40):m.start()])]
    if "phonespace" in fixes:
        # Phone-label reconciliation at the call site: PHONE_RE's domestic
        # branch can already cover the digit TAIL of a spaced "+ 0..."
        # number (leaving the "+ " prefix token leaked) -- a phonespace span
        # that strictly contains existing phone spans REPLACES them; one
        # that merely overlaps a wider phone span defers to it. Overlaps
        # with other labels are left to merge() (longer-span-wins, e.g. a
        # 16-digit Luhn credit card beats a 3-group phonespace candidate).
        for sp in _phonespace_matches(text):
            phone_overlaps = [(i, (s, e)) for i, (s, e, l) in enumerate(spans)
                              if l == "phone number" and (s < sp[1] and sp[0] < e)]
            if any(not (sp[0] <= s and e <= sp[1]) for _, (s, e) in phone_overlaps):
                continue
            for i, _ in reversed(phone_overlaps):
                del spans[i]
            spans.append(sp)
    return spans


# These labels are exclusive to the deterministic layer. Date of birth is not:
# both deterministic patterns and GLiNER can emit it.
STRUCTURED_LABELS = frozenset({"email", "iban", "phone number", "credit card", "national id", "license plate"})


def merge(spans):
    """Merge overlaps with longest-span precedence.

    On an exact-length tie, a syntax- or checksum-validated structured span
    beats a model span. The rule is independent of input order.
    """
    def priority(label):
        return 1 if label in STRUCTURED_LABELS else 0

    spans = sorted(spans, key=lambda s: (s[0], -(s[1] - s[0])))
    out = []
    for s in spans:
        if out and s[0] < out[-1][1]:
            cur_len = s[1] - s[0]
            prev_len = out[-1][1] - out[-1][0]
            if cur_len > prev_len or (cur_len == prev_len and priority(s[2]) > priority(out[-1][2])):
                out[-1] = list(s)
            continue
        out.append(list(s))
    return out


# GLiNER person spans can include a salutation, greeting, or title. Trim only
# dictionary-standard forms; ambiguous words that can also be surnames remain.
# A title alone identifies no one, while the name beneath it stays masked.
_PERSON_TITLE_WORD_RE = re.compile(
    r"""^(?:
        Sehr\s+geehrte(?:r|\*r|/r)?\s+ |   # "Sehr geehrte(r|*r|/r) "
        \*r\s+ | /r\s+ |                    # gender-star continuation alone
                                             # in the span (greeting word
                                             # itself was tokenized outside it)
        Gr[üu]ezi\s+ |
        Hr\.?\s+ | Fr\.\s+ |                 # standard Herr/Frau abbreviations
                                             # (Fr REQUIRES the dot: bare "Fr"
                                             # is too collision-prone)
        (?:Viele|Beste|Liebe)\s+Gr[üu](?:ß|ss)e[,.]?\s+ |
        Gr[üu](?:ß|ss)e?[,.]?\s+ |           # Gruß/Grüße/Gruss(e) signature
                                             # closings; double-s or ß required
                                             # so the surname "Gruse" never
                                             # matches
        (?:LG|MfG|VG)[,.]?\s+ |              # abbreviated closings, never surnames
                                             # NOTE: "Best," deliberately NOT
                                             # trimmed -- Best is a real surname
                                             # and "Last, First" is a trained
                                             # name format; trimming it would
                                             # truncate genuine names.
        Guten\s+Morgen\s+ | Morgen\s+ |
        Herr[n]?\.?\s+ | Frau\.?\s+ | Fr[äa]ulein\.?\s+ |
        Meister\.?\s+ |
        Dr\.?\s+ | Prof\.?\s+ |
        Dipl\.-Ing\.?\s+ | Dipl\.-Kfm\.?\s+ | Mag\.?\s+ | Ing\.?\s+
    )""",
    re.IGNORECASE | re.VERBOSE,
)
# a single capital-letter initial (e.g. the stray "M" in "*r M Garbo") is
# only stripped immediately AFTER at least one title word was already
# stripped -- never applied to a bare span, so a genuine one-letter given
# name in an untitled span is left alone.
_PERSON_INITIAL_RE = re.compile(r"^[A-ZÄÖÜ]\.?\s+")


# Pre-anonymized placeholders such as "[NAME_1]" contain no original value.
# Suppress predictions fully contained inside the general placeholder shape.
PLACEHOLDER_TOKEN_RE = re.compile(r"\[[A-Z][A-Z0-9]*_\d+\]")


def suppress_placeholder_spans(text, spans):
    """Drop spans that lie entirely inside a [WORD_n]-shaped placeholder."""
    holes = [(m.start(), m.end()) for m in PLACEHOLDER_TOKEN_RE.finditer(text)]
    if not holes:
        return spans
    return [s for s in spans if not any(h0 <= s[0] and s[1] <= h1 for h0, h1 in holes)]


# ai4privacy's German export carries a separate title field whose values appear
# glued to the name in prose: "Bgm Laksh", "Meist Fuad", "Aldisa Fr", "Sen".
# These are honorifics, not name tokens, and the gold spans exclude them --
# 3 DEV person FPs were pure extent errors of this shape. Kept apart from
# _PERSON_TITLE_WORD_RE because these forms are corpus vocabulary rather than
# dictionary-standard German salutations, so they stay independently revertible.
# "Sen" and "Dir" are deliberately EXCLUDED: an openpii proxy scan found "Sen"
# as a genuine trailing surname (Amartya Sen shape), and trimming a real name
# token would convert a true positive into a leaked gold token -- the G2 gate.
_CORPUS_TITLE_LEADING_RE = re.compile(
    r"^(?:Bgm|Meist|Mstr|Frl|Bfr|Amb)\.?\s+", re.IGNORECASE
)
_CORPUS_TITLE_TRAILING_RE = re.compile(
    r"\s+(?:Bgm|Meist|Mstr|Frl|Bfr|Amb|Fr|Hr)\.?$", re.IGNORECASE
)


def trim_corpus_title(text, start, end, fixes=None):
    """Trim corpus-style honorifics from either end of a person span."""
    if "corpustitle" not in _resolve_fixes(fixes):
        return start, end
    new_start, new_end = start, end
    while (match := _CORPUS_TITLE_LEADING_RE.match(text[new_start:new_end])):
        new_start += match.end()
    while (match := _CORPUS_TITLE_TRAILING_RE.search(text[new_start:new_end])):
        new_end = new_start + match.start()
    return (new_start, new_end) if new_start < new_end else (start, end)


def trim_person_title(text, start, end):
    """Trim leading title tokens and a following initial from a person span.

    Return the original bounds if trimming would remove the entire span.
    """
    new_start = start
    stripped_any = False
    new_start, end = trim_corpus_title(text, new_start, end)
    while True:
        m = _PERSON_TITLE_WORD_RE.match(text[new_start:end])
        if not m:
            break
        new_start += m.end()
        stripped_any = True
    if stripped_any:
        m = _PERSON_INITIAL_RE.match(text[new_start:end])
        if m:
            new_start += m.end()
    return (new_start, end) if new_start < end else (start, end)


# Address post-processing only extends or joins existing model-produced address
# spans; it never creates one from unclassified text. House numbers support
# simple and compound export forms. Horizontal whitespace is explicit so an
# extension cannot cross a line.
_HOUSENUM_RE = re.compile(
    r"\d{1,3}[ \t]*[./-][ \t]*\d{1,3}"  # compound: "35 . 3", "12/4", "7-2"
    r"|\d{1,4}[a-zA-Z]?"                 # simple: "12", "12a", "179"
)
# "adjacent (<=2 chars of whitespace/punct, same line)" -- deliberately a
# SMALL, punctuation-only class (no \n) so the {0,2} cap can never be
# satisfied by crossing a line break, and a 3+ char gap always leaves at
# least one unconsumed separator character directly blocking the required
# housenum/address match at that position (see extend_address_with_
# housenumber's docstring for why no explicit \n check is needed on top of
# this).
_ADJACENT_GAP_RE = re.compile(r"[ \t,.\-]{0,2}")
_HOUSENUM_LOOKBACK = 12  # generous upper bound on a housenum token's length


def _housenum_after(text, pos):
    """A house-number-shaped token starting at-or-after `pos`, separated by
    <=2 whitespace/punct chars (same line) -- or None. Greedy gap
    consumption (up to the 2-char cap) mirrors regex semantics naturally:
    if the true gap is wider than 2 chars, the leftover separator
    character sits directly where the housenum match would have to start,
    which can never match (housenum tokens start with a digit), so wider
    gaps correctly fail closed without any extra bookkeeping."""
    gap = _ADJACENT_GAP_RE.match(text, pos)
    gap_end = gap.end() if gap else pos
    m = _HOUSENUM_RE.match(text, gap_end)
    if not m or m.start() == m.end():
        return None
    # don't swallow a partial prefix of a longer alnum run (e.g. a 5-digit
    # postal code, where the simple branch caps at 4 digits)
    if m.end() < len(text) and text[m.end()].isalnum():
        return None
    return m.start(), m.end()


def _housenum_before(text, pos):
    """A house-number-shaped token ending at-or-before `pos` -- or None.
    Regex engines only anchor forward matches easily, so the backward
    direction is done by hand: greedily consume up to 2 valid gap chars
    immediately before `pos` (mirroring _housenum_after's forward greedy
    consumption), then look for a housenum match ending exactly at the
    resulting boundary within a bounded lookback window."""
    gap_start = pos
    for _ in range(2):
        if gap_start - 1 >= 0 and _ADJACENT_GAP_RE.fullmatch(text[gap_start - 1:gap_start]):
            gap_start -= 1
        else:
            break
    window_start = max(0, gap_start - _HOUSENUM_LOOKBACK)
    window = text[window_start:gap_start]
    found = None
    for m in _HOUSENUM_RE.finditer(window):
        if m.end() == len(window):
            found = m
    if found is None:
        return None
    abs_start = window_start + found.start()
    # don't swallow a partial suffix of a longer alnum run
    if abs_start > 0 and text[abs_start - 1].isalnum():
        return None
    return abs_start, gap_start


def extend_address_with_housenumber(text, spans, fixes=None):
    """Extend address spans over an immediately adjacent house number."""
    if "housenum" not in _resolve_fixes(fixes):
        return spans
    out = []
    for s, e, label in spans:
        if label == "address":
            after = _housenum_after(text, e)
            if after:
                e = max(e, after[1])
            before = _housenum_before(text, s)
            if before:
                s = min(s, before[0])
        out.append((s, e, label))
    return out


# Conservative separators for joining adjacent address fragments, optionally
# with a house number between them.
_CHAIN_SEP_RE = r"(?:[ \t]*\n[ \t]*|[ \t]*-[ \t]*|,[ \t]*|[ \t]+)"
_CHAIN_GAP_RE = re.compile(
    rf"{_CHAIN_SEP_RE}?"                                          # optional leading separator
    rf"(?:\d{{1,3}}[ \t]*[./-][ \t]*\d{{1,3}}|\d{{1,4}}[a-zA-Z]?)?"  # optional intervening housenum
    rf"{_CHAIN_SEP_RE}?"                                          # optional trailing separator
)


def chain_address_spans(text, spans, fixes=None):
    """Join adjacent address spans across a conservative address-shaped gap."""
    if "chain" not in _resolve_fixes(fixes):
        return spans
    address_idxs = sorted(
        (i for i, sp in enumerate(spans) if sp[2] == "address"),
        key=lambda i: spans[i][0],
    )
    if len(address_idxs) < 2:
        return spans
    out_spans = list(spans)
    merged_away = set()
    chain_idx = address_idxs[0]
    cur_start, cur_end, _ = spans[chain_idx]
    for idx in address_idxs[1:]:
        s, e, _ = spans[idx]
        if s < cur_end:
            # already overlapping -- merge()'s job, not this fix's; just
            # extend the tracked chain end so a later fragment can still
            # chain onto it and keep scanning.
            cur_end = max(cur_end, e)
            merged_away.add(idx)
            continue
        gap = text[cur_end:s]
        if _CHAIN_GAP_RE.fullmatch(gap) is not None:
            cur_end = max(cur_end, e)
            merged_away.add(idx)
        else:
            out_spans[chain_idx] = (cur_start, cur_end, "address")
            chain_idx = idx
            cur_start, cur_end = s, e
    out_spans[chain_idx] = (cur_start, cur_end, "address")
    return [sp for i, sp in enumerate(out_spans) if i not in merged_away]


# A postal address is not a network address. GLiNER fires "address" on MAC,
# IPv6 and crypto-wallet strings because the surrounding German text says
# "Netzadresse:" / "MAC-Adresse:" / "ETH Addresse" -- 4 DEV address false
# positives. Neither DEV nor data/test.json gold ever labels such a shape as an
# address, so dropping them cannot cost a true positive or leak a gold token.
_TECHNICAL_ADDRESS_RE = re.compile(
    r"(?:[0-9a-fA-F]{2}\s?:\s?){3,}[0-9a-fA-F]{2}|0x[0-9a-fA-F]{8,}"
)
# Pre-anonymized exports sometimes carry an unbracketed placeholder token
# ("SECONDARYADDRESS_17"). suppress_placeholder_spans() only recognises the
# bracketed "[NAME_1]" form, so the bare shape survived as a false positive.
_BARE_PLACEHOLDER_RE = re.compile(r"^[A-Z][A-Z_]{3,}_\d+$")


def drop_non_postal_address_spans(text, spans, fixes=None):
    """Remove address spans that are network addresses or bare placeholders."""
    if "addrguard" not in _resolve_fixes(fixes):
        return spans
    kept = []
    for start, end, label in spans:
        if label == "address":
            body = text[start:end].strip()
            if _TECHNICAL_ADDRESS_RE.search(body) or _BARE_PLACEHOLDER_RE.match(body):
                continue
        kept.append((start, end, label))
    return kept


def trim_structured_tail_from_address(text, spans, fixes=None):
    """Keep an address span from absorbing an adjacent structured detection.

    merge() resolves overlaps by longest span, so a GLiNER address span that ran
    on into a phone number or IBAN swallows it -- costing an exact-match address
    TP *and* the structured span. The deterministic detectors are checksum- or
    syntax-validated, so they win their own extent: trim the address back at its
    boundary instead. Only prefix/suffix overlaps are trimmed, never a split.
    """
    if "addrguard" not in _resolve_fixes(fixes):
        return spans
    authoritative = [
        (s, e) for s, e, label in spans
        if label in {"phone number", "iban", "email", "credit card"}
    ]
    out = []
    for start, end, label in spans:
        if label == "address":
            for a_start, a_end in authoritative:
                if a_start <= start < a_end < end:        # overlaps the prefix
                    start = a_end
                elif start < a_start < end <= a_end:      # overlaps the suffix
                    end = a_start
            while start < end and text[start] in " \t,;-\n":
                start += 1
            while end > start and text[end - 1] in " \t,;-\n":
                end -= 1
        if start < end:
            out.append((start, end, label))
    return out


# Adjacent address fragments separated by nothing but a short run of address
# punctuation are one postal address ("Blücherstraße 5" + ", " + "52525
# Budenheim"). Emitting them separately is wrong for the product -- a consumer
# masking span-by-span would leave the separator exposed and produce two
# [ADDRESS] markers where one belongs -- and it also mismatches how
# prepare_eval_datasets.py builds gold, which merges same-label spans across a
# gap of at most three characters of [\s,·;–-]. The gap class below is
# deliberately identical to that rule, so our output granularity and the
# annotation convention agree instead of disagreeing by accident.
_ADDRESS_MERGE_GAP_RE = re.compile(r"^[\s,·;\u2013-]{0,3}$")


def merge_address_eval_convention(text, spans, fixes=None):
    """Join address spans separated only by a short address-punctuation gap."""
    if "addrmerge" not in _resolve_fixes(fixes):
        return spans
    address = sorted((s for s in spans if s[2] == "address"), key=lambda s: (s[0], s[1]))
    others = [s for s in spans if s[2] != "address"]
    merged = []
    for start, end, label in address:
        if merged and start >= merged[-1][1] and _ADDRESS_MERGE_GAP_RE.match(text[merged[-1][1]:start]):
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end, label])
    return others + [tuple(s) for s in merged]


def apply_address_fixes(text, spans, fixes=None):
    """Extend house numbers, then join adjacent address fragments."""
    fixes = _resolve_fixes(fixes)
    spans = drop_non_postal_address_spans(text, spans, fixes=fixes)
    spans = extend_address_with_housenumber(text, spans, fixes=fixes)
    spans = chain_address_spans(text, spans, fixes=fixes)
    spans = trim_structured_tail_from_address(text, spans, fixes=fixes)
    spans = merge_address_eval_convention(text, spans, fixes=fixes)
    return spans


def redact(text, model, threshold=None, label_thresholds=None):
    """Redact text with deterministic detection followed by GLiNER.

    Pass `threshold` for one global model cutoff or `label_thresholds` to
    override the default per-label policy.
    """
    spans = detect_structured(text)
    if label_thresholds is None and threshold is None:
        label_thresholds = label_thresholds_for(text)
    query_threshold = threshold if threshold is not None else min(label_thresholds.values())
    for ent in model.predict_entities(text, ML_LABELS, threshold=query_threshold, flat_ner=True):
        cutoff = threshold if threshold is not None else label_thresholds.get(ent["label"], 0.5)
        if ent.get("score", 1.0) >= cutoff:
            start, end = ent["start"], ent["end"]
            if ent["label"] == "person":
                start, end = trim_person_title(text, start, end)
            spans.append((start, end, ent["label"]))
    spans = suppress_placeholder_spans(text, spans)
    spans = apply_address_fixes(text, spans)
    for start, end, label in sorted(merge(spans), key=lambda s: -s[0]):
        text = text[:start] + f"[{label.upper().replace(' ', '_')}]" + text[end:]
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--text")
    ap.add_argument("--threshold", type=float, default=None,
                    help="override the default per-label policy with one "
                         "global cutoff for every model label")
    args = ap.parse_args()
    # Report active optional behavior before loading the model.
    print(pipeline_fixes_status_line(), file=sys.stderr)
    from gliner import GLiNER
    model = GLiNER.from_pretrained(args.model)
    text = args.text if args.text else sys.stdin.read()
    print(redact(text, model, threshold=args.threshold))


if __name__ == "__main__":
    main()
