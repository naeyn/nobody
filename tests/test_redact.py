import pytest

from redact import (
    active_pipeline_fixes,
    apply_address_fixes,
    bsn_valid,
    chain_address_spans,
    detect_structured,
    extend_address_with_housenumber,
    has_german_business_register,
    iban_valid,
    label_thresholds_for,
    looks_german,
    luhn_valid,
    pipeline_fixes_status_line,
    suppress_placeholder_spans,
    merge,
    steuerid_valid,
    trim_person_title,
)


def test_checksums_accept_valid_and_reject_changed_values():
    assert iban_valid("DE89370400440532013000")
    assert not iban_valid("DE89370400440532013001")
    assert luhn_valid("4111 1111 1111 1111")
    assert not luhn_valid("4111 1111 1111 1112")
    assert steuerid_valid("89706244312")
    assert not steuerid_valid("89706244313")
    assert bsn_valid("111222333")
    assert not bsn_valid("111222334")


def test_structured_detector_emits_validated_layers():
    text = (
        "Kontakt anna@example.de, +49 30 1234567, "
        "IBAN DE89370400440532013000, Karte 4111 1111 1111 1111, "
        "Steuer-ID 89706244312, BSN 111222333, Kennzeichen B-AB 1234"
    )
    labels = {label for _, _, label in detect_structured(text)}

    assert {"email", "phone number", "iban", "credit card", "national id", "license plate"} <= labels

def test_iban_detection_is_case_insensitive():
    spans = detect_structured("IBAN de89370400440532013000")
    assert any(label == "iban" for _, _, label in spans)

def test_phone_detection_accepts_parenthesized_area_code():
    spans = detect_structured("Rückruf unter ( 06 ) 5503-5880")
    assert any(label == "phone number" for _, _, label in spans)


def test_phone_detection_does_not_span_across_a_line_break():
    # Whitespace matching must not consume digits on the following line.
    text = "Tel. +44 7133 924265\n65 Owens Mall"
    spans = [text[s:e] for s, e, label in detect_structured(text) if label == "phone number"]
    assert spans == ["+44 7133 924265"]

def test_email_detection_accepts_export_domain_punctuation():
    text = "ter rehorst3@outlook.com support@schofield,.com"
    spans = detect_structured(text)
    assert any(label == "email" and "schofield" in text[s:e]
               for s, e, label in spans)


def test_email_detection_accepts_unicode_domain():
    # Unicode domains must not depend on an ASCII-only character class.
    text = "An: support@röhricht.com und cc support@süßebier.com"
    spans = {text[s:e] for s, e, label in detect_structured(text) if label == "email"}
    assert "support@röhricht.com" in spans
    assert "support@süßebier.com" in spans


def test_email_detection_accepts_unicode_local_part():
    # Unicode support applies to the local part as well as the domain.
    text = "E-Mail: 2003anna-sofia.wäcker@tutanota.com"
    spans = {text[s:e] for s, e, label in detect_structured(text) if label == "email"}
    assert "2003anna-sofia.wäcker@tutanota.com" in spans


def test_email_detection_accepts_multiword_local_part():
    # Surname particles can appear as spaces in generated local parts.
    text = "Von: Benthe van der Laarse <van der laarse94@outlook.com>"
    spans = {text[s:e] for s, e, label in detect_structured(text) if label == "email"}
    assert "van der laarse94@outlook.com" in spans


def test_email_detection_does_not_run_away_into_preceding_sentence():
    # the multi-word local-part allowance is capped at 3 extra segments so
    # it can't swallow an entire preceding sentence just because it ends
    # near an @ handle.
    text = "Wir haben das Angebot besprochen und einen neuen Termin vereinbart und schicken es an anna@example.de"
    spans = [text[s:e] for s, e, label in detect_structured(text) if label == "email"]
    assert spans == ["anna@example.de"]


def test_invalid_checksum_is_not_detected():
    text = "IBAN DE89370400440532013001 Karte 4111 1111 1111 1112"
    assert not [span for span in detect_structured(text) if span[2] in {"iban", "credit card"}]


def test_looks_german_detects_german_prose():
    assert looks_german("Ich bin der Meinung, dass wir uns nicht sicher sind, ob es sich lohnt.")


def test_looks_german_rejects_english_prose():
    assert not looks_german("I am reaching out regarding the invoice that was sent last week.")


def test_looks_german_rejects_short_or_empty_text():
    assert not looks_german("")
    assert not looks_german("ID4711")


def test_label_thresholds_are_flat_across_languages():
    # Production thresholds are independent of benchmark taxonomies.
    de_thresholds = label_thresholds_for("Ich wohne in Berlin und bin mir dabei nicht sicher.")
    en_thresholds = label_thresholds_for("I work at Acme Corp and live in London.")

    assert de_thresholds == en_thresholds == label_thresholds_for("")
    for lt in (de_thresholds, en_thresholds):
        assert lt["person"] <= 0.5
        assert lt["address"] <= 0.2
        assert lt["date of birth"] <= 0.5
        assert 0.0 < lt["organization"] <= 1.0


def test_german_business_register_cue_detected():
    assert has_german_business_register("Bitte wenden Sie sich an die Müller GmbH in Köln.")
    assert has_german_business_register("Rechnung von Schmidt AG, vielen Dank.")
    assert has_german_business_register("Kontakt: Weber & Partner e.V.")


def test_german_personal_record_has_no_business_register_cue():
    assert not has_german_business_register(
        "Ich bin der Meinung, dass wir uns nicht sicher sind, geboren am 5. Juni 1963."
    )


def test_label_thresholds_same_for_personal_and_business_register_text():
    # A business-register cue must not alter the production policy.
    personal = label_thresholds_for("Ich wohne in Berlin und bin bei der Sache nicht sicher.")
    business = label_thresholds_for("Bitte kontaktieren Sie die Müller GmbH bezüglich der Rechnung.")
    assert personal == business


def test_label_thresholds_mixed_language_edge_case_falls_back_safely():
    # a short, mixed or ambiguous document should not crash and should default
    # to the safer (organization-enabled) policy, since looks_german() is
    # deliberately conservative about firing on sparse/ambiguous text
    mixed = "Invoice #4711 - Kontakt: anna@example.de - Thanks, Anna"
    thresholds = label_thresholds_for(mixed)
    assert set(thresholds) == {"person", "address", "date of birth", "organization"}
    assert 0.0 < thresholds["organization"] <= 1.5


# Structured detections win exact-span ties with model predictions.

def test_merge_prefers_structured_email_over_gliner_person_on_exact_tie():
    # The result must be independent of caller insertion order.
    text = "Bitte Antwort an J@tutanota.com."
    s = text.index("J@tutanota.com")
    e = s + len("J@tutanota.com")
    gliner_first = merge([(s, e, "person")] + detect_structured(text))
    structured_first = merge(detect_structured(text) + [(s, e, "person")])
    for result in (gliner_first, structured_first):
        labels = {l for _, _, l in result}
        assert "email" in labels
        assert "person" not in labels


def test_merge_prefers_structured_email_over_gliner_address_on_exact_tie():
    # A structured email beats an equal-length model address.
    text = "E-Mail: 2003anna-sofia.wäcker@tutanota.com Country: Schweiz"
    s = text.index("2003anna-sofia")
    e = s + len("2003anna-sofia.wäcker@tutanota.com")
    result = merge([(s, e, "address")] + detect_structured(text))
    labels = {l for _, _, l in result}
    assert "email" in labels
    assert "address" not in labels


def test_merge_prefers_structured_phone_over_gliner_address_on_exact_tie():
    # A structured phone number beats an equal-length model address.
    text = "senden Sie die Bankdetails inkl. Telefonnummer 059 128.9643 und ID"
    s = text.index("059 128.9643")
    e = s + len("059 128.9643")
    result = merge([(s, e, "address")] + detect_structured(text))
    labels = {l for _, _, l in result}
    assert "phone number" in labels
    assert "address" not in labels


def test_merge_same_label_tie_is_unaffected_by_priority():
    # two "date of birth" spans (one could be regex-origin, one GLiNER-origin)
    # at the same position: priority only matters across DIFFERENT labels, so
    # this must behave exactly as before (longer wins, else first survives).
    result = merge([(0, 10, "date of birth"), (0, 10, "date of birth")])
    assert result == [[0, 10, "date of birth"]]


def test_merge_still_prefers_longer_span_regardless_of_priority():
    # priority is only a TIE-break; a longer GLiNER span still beats a
    # shorter structured one that merely overlaps it.
    result = merge([(0, 5, "email"), (0, 20, "person")])
    assert result == [[0, 20, "person"]]


# Person-title trimming

def test_trim_person_title_strips_single_honorific():
    text = "Herr Dr Nekibe wurde in der Studie gelistet."
    s, e = text.index("Dr Nekibe"), text.index("Dr Nekibe") + len("Dr Nekibe")
    assert trim_person_title(text, s, e) == (text.index("Nekibe"), e)


def test_trim_person_title_strips_stacked_titles():
    # multi-title stack: "Herr Prof. Dr." all in the predicted span.
    text = "Kontakt: Herr Prof. Dr. Müller-Weiss ist zustaendig."
    span_text = "Herr Prof. Dr. Müller-Weiss"
    s = text.index(span_text)
    e = s + len(span_text)
    ns, ne = trim_person_title(text, s, e)
    assert text[ns:ne] == "Müller-Weiss"


def test_trim_person_title_handles_umlaut_name_offsets():
    # Unicode before and inside the span must preserve character offsets.
    text = "Für Rückfragen wenden Sie sich an Frau Müller-Schäfer."
    span_text = "Frau Müller-Schäfer"
    s = text.index(span_text)
    e = s + len(span_text)
    ns, ne = trim_person_title(text, s, e)
    assert text[ns:ne] == "Müller-Schäfer"
    assert ne == e  # end untouched
    assert text[ns] == "M"


def test_trim_person_title_strips_gender_star_and_stray_initial():
    # Tokenization can split a gender-star greeting before a stray initial.
    text = "<p>Sehr geehrte*r M Garbo, wir benötigen Ihre Kreditwürdigkeit."
    span_text = "*r M Garbo"
    s = text.index(span_text)
    e = s + len(span_text)
    ns, ne = trim_person_title(text, s, e)
    assert text[ns:ne] == "Garbo"


def test_trim_person_title_does_not_strip_bare_initial_without_a_title():
    # a lone capitalized initial with NO preceding title word must be left
    # alone -- the initial-strip only fires after a title word was stripped.
    text = "Kontakt: M Garbo hat unterschrieben."
    span_text = "M Garbo"
    s = text.index(span_text)
    e = s + len(span_text)
    assert trim_person_title(text, s, e) == (s, e)


def test_trim_person_title_falls_back_when_span_is_title_only():
    # Leave a span unchanged if trimming would remove its entire content.
    text = "Sehr geehrter Senator, bitte teilen Sie mit."
    span_text = "Senator"
    s = text.index(span_text)
    e = s + len(span_text)
    assert trim_person_title(text, s, e) == (s, e)


def test_trim_person_title_no_op_on_untitled_span():
    text = "Anna Berger hat angerufen."
    s, e = 0, len("Anna Berger")
    assert trim_person_title(text, s, e) == (s, e)


# IMEI and credit-card Luhn collision

def test_imei_cue_suppresses_15_digit_credit_card_tag():
    text = ("Sehr geehrte Antragsteller, für den Abschluss Ihrer "
            "Design-Patent-Anmeldung benötigen wir Ihre IPV6-Adresse [IPV6_1] "
            "und die zugehörige IMEI-Nummer 803774110320065. Besuchen Sie "
            "bitte https://www.schinke.org/ für weitere Schritte.")
    labels = {l for _, _, l in detect_structured(text)}
    assert "credit card" not in labels


def test_imei_cue_does_not_suppress_unrelated_15_digit_credit_card():
    text = "Bitte pruefen Sie die Kartennummer 728261038651815 zeitnah."
    labels = {l for _, _, l in detect_structured(text)}
    assert "credit card" in labels


def test_imei_cue_does_not_suppress_16_digit_card_far_from_an_imei_mention():
    # the suppression is scoped to the exact 15-digit collision; a
    # 16-digit card elsewhere in a document that separately mentions IMEI
    # somewhere far away must still be tagged.
    text = ("Das IMEI-Geraet wurde vor Monaten registriert. " + "x" * 40 +
            " Kartennummer: 4111 1111 1111 1111.")
    labels = {l for _, _, l in detect_structured(text)}
    assert "credit card" in labels


# Cue-gated unprefixed phone formats

def test_cue_gated_phone_detects_bare_digit_group_formats():
    cases = [
        "MI-Kontrollstrategien für Telefonnummer 1482.813.1965.",
        "Bewertung: Ausgezeichnet, Telefonnummer: 3163-001-6631.",
        "verwendet die Telefonnummer 8573 636 7367. Kreditkartendaten - Ablauf.",
        "5864 synchronisiert ist. Ruf mich unter 1251-309.6675 an, sollten Probleme auftreten.",
    ]
    for text in cases:
        spans = [text[s:e] for s, e, l in detect_structured(text) if l == "phone number"]
        assert spans, f"expected a phone match in: {text!r}"


def test_cue_gated_phone_does_not_fire_without_a_phone_cue():
    # The same digit shape without a phone cue must not match.
    text = "Kundennummer: 2025-12345 bitte im Betreff angeben."
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "phone number"]
    assert spans == []


def test_cue_gated_phone_does_not_collide_with_dates():
    # DD.MM.YYYY dates near a phone cue word must not be misdetected as
    # phone numbers -- the first group must be 3-4 digits, which a day (1-2
    # digits) never is.
    text = "Der Termin ist am 17.02.2013 fuer die Telefonnummer."
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "phone number"]
    assert spans == []


def test_cue_gated_phone_does_not_collide_with_trap_numbers_near_cue():
    # Letter-prefixed and two-group order numbers must not match.
    text = "Telefonnummer siehe Ticket K-45213 und Auftrag 2025-12345."
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "phone number"]
    assert spans == []


def test_phone_detection_still_does_not_span_across_a_line_break_with_new_pattern():
    # The cue-gated pattern must preserve newline safety.
    text = "Telefonnummer:\n1482.813.1965 und 65 Owens Mall"
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "phone number"]
    assert all("\n" not in s for s in spans)


def test_phone_regex_does_not_claim_leading_zero_day_dates():
    # Domestic phone syntax can resemble leading-zero dates; filter dates at
    # detection time.
    for text in [
        "Sie ist am 05/12/1990 geboren.",
        "Geburtsdatum: 07.03.1985, Wohnort Berlin.",
        "geb. 01-01-2000 in Hamburg",
    ]:
        spans = [text[s:e] for s, e, l in detect_structured(text) if l == "phone number"]
        assert spans == [], f"date misdetected as phone in: {text!r}"


def test_phone_regex_still_detects_real_domestic_numbers():
    # the date-shape filter must not eat genuine domestic formats
    for text in [
        "Rufen Sie uns an: 030/12345678",
        "Tel. 0176 23456789",
        "Zentrale: (030) 555-1234",
    ]:
        spans = [text[s:e] for s, e, l in detect_structured(text) if l == "phone number"]
        assert spans, f"real phone missed in: {text!r}"


def test_numeric_full_dates_are_claimed_as_dob_not_phone():
    # Recall-first date detection must not also label dates as phone numbers.
    for text in [
        "Sie ist am 05/12/1990 geboren.",
        "Geburtsdatum: 07.03.1985, Wohnort Berlin.",
        "geb. 01-01-2000 in Hamburg",
        "Datum: 29 / 07 / 1968 laut Export.",
    ]:
        labels = {l for _, _, l in detect_structured(text)}
        assert "date of birth" in labels, f"numeric date not claimed as DOB: {text!r}"
        assert "phone number" not in labels, f"date tagged as phone: {text!r}"


def test_spaced_monthname_date_is_detected():
    text = "Der Stichtag 17 . Februar 2013 steht im Formular."
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "date of birth"]
    assert spans, "spaced month-name date missed"


def test_numeric_dob_does_not_eat_real_phone_numbers():
    text = "Rufen Sie uns an: 030/12345678 oder 0176 23456789."
    dob = [text[s:e] for s, e, l in detect_structured(text) if l == "date of birth"]
    phones = [text[s:e] for s, e, l in detect_structured(text) if l == "phone number"]
    assert dob == []
    assert len(phones) == 2


def test_trim_person_title_strips_frau_abbreviation_with_dot_only():
    # "Fr. Szaruga" -> "Szaruga"; bare "Fr" without dot must NOT trim
    text = "Rueckfrage von Fr. Szaruga zur Rechnung."
    s, e = text.index("Fr."), text.index("Szaruga") + len("Szaruga")
    assert text[slice(*trim_person_title(text, s, e))] == "Szaruga"
    text2 = "Fr Szaruga"  # no dot: leave untouched
    assert text2[slice(*trim_person_title(text2, 0, len(text2)))] == "Fr Szaruga"


def test_trim_person_title_strips_german_signature_closings():
    for closing, name in [("Viele Grüße ", "Kolahmad"), ("Gruß ", "Meyer"), ("MfG, ", "Yilmaz")]:
        text = f"...melde mich morgen. {closing}{name}"
        s = text.index(closing)
        got = text[slice(*trim_person_title(text, s, len(text)))]
        assert got == name, f"{closing!r}: got {got!r}"


def test_trim_person_title_never_trims_best_or_gruse_surnames():
    # "Best" is a real surname and "Last, First" is a trained name format;
    # "Gruse" is a rare surname that must not match the Gruß/Grüße pattern.
    for span_text in ["Best, Konrad", "Gruse Marie"]:
        text = f"Unterlagen von {span_text} eingereicht."
        s = text.index(span_text)
        got = text[slice(*trim_person_title(text, s, s + len(span_text)))]
        assert got == span_text, f"wrongly trimmed {span_text!r} -> {got!r}"


def test_placeholder_spans_are_suppressed():
    text = "Kontakt: [NAME_1], erreichbar unter [IPV4_2] oder j@web.de"
    n0 = text.index("[NAME_1]")
    i0 = text.index("[IPV4_2]")
    spans = [
        (n0, n0 + len("[NAME_1]"), "person"),        # inside placeholder -> drop
        (i0 + 1, i0 + 7, "address"),                  # strictly inside -> drop
        (text.index("j@web.de"), len(text), "email"), # real -> keep
        (n0 - 9, n0 + 3, "person"),                   # straddles boundary -> keep
    ]
    out = suppress_placeholder_spans(text, spans)
    assert (text.index("j@web.de"), len(text), "email") in out
    assert (n0 - 9, n0 + 3, "person") in out
    assert len(out) == 2


# Optional pipeline-fix controls

def test_active_pipeline_fixes_defaults_to_all_when_unset(monkeypatch):
    monkeypatch.delenv("NOBODY_PIPELINE_FIXES", raising=False)
    assert active_pipeline_fixes() == {"chain", "housenum", "dobslash", "spacedemail", "phonespace",
                                       "buildingnum", "corpustitle", "addrguard", "addrmerge"}


def test_active_pipeline_fixes_empty_string_means_none(monkeypatch):
    monkeypatch.setenv("NOBODY_PIPELINE_FIXES", "")
    assert active_pipeline_fixes() == frozenset()


def test_active_pipeline_fixes_comma_list_selects_exact_subset(monkeypatch):
    monkeypatch.setenv("NOBODY_PIPELINE_FIXES", "chain,housenum")
    assert active_pipeline_fixes() == {"chain", "housenum"}


def test_active_pipeline_fixes_rejects_unknown_name(monkeypatch):
    monkeypatch.setenv("NOBODY_PIPELINE_FIXES", "chain,typo")
    with pytest.raises(ValueError):
        active_pipeline_fixes()


def test_pipeline_fixes_status_line_formats_sorted_list_or_none():
    assert pipeline_fixes_status_line(fixes=frozenset()) == "pipeline fixes active: NONE"
    assert (pipeline_fixes_status_line(fixes={"spacedemail", "chain"})
            == "pipeline fixes active: chain, spacedemail")
    assert (pipeline_fixes_status_line(fixes={"chain", "housenum", "dobslash", "spacedemail"})
            == "pipeline fixes active: chain, dobslash, housenum, spacedemail")


# Month-name slash date forms

def test_dob_slash_form_detects_examples():
    for example in ["Juni / 36", "Juni / 52", "Dezember / 21", "August / 53", "Oktober / 64"]:
        spans = detect_structured(f"Geburtsdatum laut Akte: {example} eingetragen.")
        matches = [(s, e) for s, e, l in spans if l == "date of birth"]
        assert matches, f"missed: {example!r}"
        text = f"Geburtsdatum laut Akte: {example} eingetragen."
        s, e = matches[0]
        assert text[s:e] == example, f"boundary off for {example!r}: got {text[s:e]!r}"


def test_dob_slash_form_symmetric_reverse_order():
    text = "Vermerkt: 26 / Juni laut Formular."
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "date of birth"]
    assert "26 / Juni" in spans


def test_dob_slash_form_does_not_match_invoice_context():
    text = "Rechnung 123/2024 liegt bei."
    spans = [l for _, _, l in detect_structured(text) if l == "date of birth"]
    assert spans == []


def test_dob_slash_form_does_not_disturb_iso_dates_already_covered():
    text = "geb. 1947-03-23T00:00:00 in Koeln"
    spans = [(text[s:e], l) for s, e, l in detect_structured(text) if l == "date of birth"]
    assert spans == [("1947-03-23T00:00:00", "date of birth")]


def test_dob_slash_form_bound_does_not_extend_into_surrounding_digits():
    # word-boundary requirement: a slash-adjacent 2-digit run that is really
    # part of a longer digit run (not a clean \b\d{2}\b) must not match.
    text = "Aktenzeichen 1123 / Juni 45678 wurde erfasst."
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "date of birth"]
    assert spans == []


def test_dob_slash_form_off_when_fix_toggled_off():
    text = "Geburtsdatum laut Akte: Juni / 36 eingetragen."
    spans = [l for _, _, l in detect_structured(text, fixes=frozenset()) if l == "date of birth"]
    assert spans == []
    # explicit subset without "dobslash" also leaves it off
    spans2 = [l for _, _, l in detect_structured(text, fixes={"chain", "housenum", "spacedemail"})
              if l == "date of birth"]
    assert spans2 == []


# Spaced email forms

def test_spaced_email_detects_verbatim_example():
    text = "Kontakt: j . doe @ web . de bitte."
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "email"]
    assert spans == ["j . doe @ web . de"]


def test_spaced_email_does_not_match_dot_at_punctuation_coincidence():
    text = "Der Termin endet um 17 Uhr . @ dem Empfang bitte melden."
    spans = [l for _, _, l in detect_structured(text) if l == "email"]
    assert spans == []


def test_spaced_email_rejects_multi_space_runs():
    text = "Kontakt: j .  doe  @ web . de bitte."  # double spaces around some separators
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "email"]
    assert spans == []


def test_spaced_email_does_not_run_away_into_following_sentence():
    # regression test for a real bug found during development: an earlier
    # version's unbounded domain-repetition group matched "web . de.
    # Rechnung" (swallowing the START of the next sentence) because a
    # sentence-ending period is syntactically identical to a spaced domain
    # dot. See the BUG FOUND comment above SPACED_EMAIL_RE.
    text = "Kontakt: j . doe @ web . de. Rechnung 123/2024 liegt bei."
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "email"]
    assert spans == ["j . doe @ web . de"]


def test_spaced_email_local_part_does_not_run_away_into_preceding_sentence():
    # symmetric regression: the local part's optional dot-segment must not
    # absorb an unrelated preceding sentence fragment ending in ". Word".
    text = "Ich habe die Anfrage. Antwort @ web.de"
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "email"]
    for span in spans:
        assert "Anfrage" not in span, f"local part over-extended: {span!r}"


def test_spaced_email_does_not_duplicate_a_normal_email_match():
    # a normal, non-spaced email must still produce exactly ONE "email"
    # span (SPACED_EMAIL_RE's own matches that overlap an EMAIL_RE match
    # are suppressed at the detect_structured() level, not left for
    # merge() to deduplicate).
    text = "Kontakt anna@example.de bitte."
    spans = [(s, e) for s, e, l in detect_structured(text) if l == "email"]
    assert len(spans) == 1
    assert text[spans[0][0]:spans[0][1]] == "anna@example.de"


def test_spaced_email_off_when_fix_toggled_off():
    text = "Kontakt: j . doe @ web . de bitte."
    spans = [l for _, _, l in detect_structured(text, fixes=frozenset()) if l == "email"]
    assert spans == []


# House-number adjacency

def test_housenum_adjacency_extends_trailing_simple_number():
    text = "Wohnhaft in Musterstraße 12 seit 2020."
    addr_end = text.index("Musterstraße") + len("Musterstraße")
    spans = [(text.index("Musterstraße"), addr_end, "address")]
    (s, e, label), = extend_address_with_housenumber(text, spans)
    assert label == "address"
    assert text[s:e] == "Musterstraße 12"


def test_housenum_adjacency_extends_trailing_compound_number():
    # Compound export form with spacing.
    text = "Anschrift: Musterweg 35 . 3, weitere Angaben folgen."
    addr_start = text.index("Musterweg")
    addr_end = addr_start + len("Musterweg")
    spans = [(addr_start, addr_end, "address")]
    (s, e, label), = extend_address_with_housenumber(text, spans)
    assert text[s:e] == "Musterweg 35 . 3"


def test_housenum_adjacency_extends_leading_number_both_directions():
    text = "12 Musterstraße ist die Anschrift."
    addr_start = text.index("Musterstraße")
    addr_end = addr_start + len("Musterstraße")
    spans = [(addr_start, addr_end, "address")]
    (s, e, label), = extend_address_with_housenumber(text, spans)
    assert text[s:e] == "12 Musterstraße"


def test_housenum_adjacency_does_not_fire_without_an_adjacent_address():
    # must NOT invent a new address span, or attach to an unrelated
    # nearby span of a different label.
    text = "Bestellnummer 12 wurde versendet."
    spans = [(0, 0, "organization")]
    out = extend_address_with_housenumber(text, spans)
    assert out == spans


def test_housenum_adjacency_does_not_swallow_a_longer_digit_run():
    # a 5-digit postal code right after the street name must not be
    # partially eaten as if it were a (max 4-digit) house number.
    text = "Musterstraße 12345 Musterstadt"
    spans = [(0, len("Musterstraße"), "address")]
    (s, e, label), = extend_address_with_housenumber(text, spans)
    assert text[s:e] == "Musterstraße"


def test_housenum_adjacency_does_not_fire_across_a_wide_gap():
    text = "Musterstraße     12"  # 5 spaces: > the 2-char gap allowance
    spans = [(0, len("Musterstraße"), "address")]
    out = extend_address_with_housenumber(text, spans)
    assert out == spans


def test_housenum_adjacency_off_when_fix_toggled_off():
    text = "Wohnhaft in Musterstraße 12 seit 2020."
    addr_end = text.index("Musterstraße") + len("Musterstraße")
    spans = [(text.index("Musterstraße"), addr_end, "address")]
    out = extend_address_with_housenumber(text, spans, fixes=frozenset())
    assert out == spans


# Address chaining

def test_address_chaining_merges_simple_adjacent_spans():
    text = "Musterstraße 5, 12345 Berlin bitte beachten."
    a1 = (0, len("Musterstraße 5"), "address")
    a2_start = text.index("12345")
    a2 = (a2_start, a2_start + len("12345 Berlin"), "address")
    (s, e, label), = chain_address_spans(text, [a1, a2])
    assert text[s:e] == "Musterstraße 5, 12345 Berlin"


def test_address_chaining_absorbs_intervening_housenumber():
    text = "Anschrift Musterstraße, 12, 12345 Musterstadt endet hier."
    b1_start = text.index("Musterstraße")
    b1 = (b1_start, b1_start + len("Musterstraße"), "address")
    b2_start = text.index("12345")
    b2 = (b2_start, b2_start + len("12345 Musterstadt"), "address")
    (s, e, label), = chain_address_spans(text, [b1, b2])
    assert text[s:e] == "Musterstraße, 12, 12345 Musterstadt"


def test_address_chaining_does_not_merge_across_unrelated_text():
    text = "Musterstraße wurde 1998 gegruendet und ist bekannt fuer 12345 Musterstadt Angebote."
    c1 = (0, len("Musterstraße"), "address")
    c2_start = text.index("12345")
    c2 = (c2_start, c2_start + len("12345 Musterstadt"), "address")
    out = chain_address_spans(text, [c1, c2])
    assert sorted(out) == sorted([c1, c2])  # both spans survive, unmerged


def test_address_chaining_off_when_fix_toggled_off():
    text = "Musterstraße 5, 12345 Berlin bitte beachten."
    a1 = (0, len("Musterstraße 5"), "address")
    a2_start = text.index("12345")
    a2 = (a2_start, a2_start + len("12345 Berlin"), "address")
    out = chain_address_spans(text, [a1, a2], fixes=frozenset())
    assert sorted(out) == sorted([a1, a2])


def test_apply_address_fixes_combines_housenum_then_chain():
    # the two fixes compose: housenum-extension pulls the intervening "12"
    # into the first address span, then chaining links the (now-extended)
    # spans across the remaining ", " gap -- same end result either way
    # (verified against running chain alone, which does its own
    # independent housenum absorption -- see chain_address_spans' docstring).
    text = "Anschrift Musterstraße, 12, 12345 Musterstadt endet hier."
    b1_start = text.index("Musterstraße")
    b1 = (b1_start, b1_start + len("Musterstraße"), "address")
    b2_start = text.index("12345")
    b2 = (b2_start, b2_start + len("12345 Musterstadt"), "address")
    (s, e, label), = apply_address_fixes(text, [b1, b2])
    assert text[s:e] == "Musterstraße, 12, 12345 Musterstadt"


def test_apply_address_fixes_all_off_is_a_pure_passthrough():
    text = "Anschrift Musterstraße, 12, 12345 Musterstadt endet hier."
    b1_start = text.index("Musterstraße")
    b1 = (b1_start, b1_start + len("Musterstraße"), "address")
    b2_start = text.index("12345")
    b2 = (b2_start, b2_start + len("12345 Musterstadt"), "address")
    out = apply_address_fixes(text, [b1, b2], fixes=frozenset())
    assert sorted(out) == sorted([b1, b2])


# All optional fixes disabled

def test_fixes_off_disables_optional_detection_exactly():
    # One fixture covers address extension/chaining, month-slash dates, spaced
    # email, and an invoice-number negative case.
    text = (
        "Herr Dr Nekibe wohnt in Musterstraße 12, 12345 Musterstadt. "
        "Geboren im Juni / 36 laut Akte. Kontakt: j . doe @ web . de. "
        "Rechnung 123/2024 liegt bei. IBAN DE89370400440532013000. "
        "Platzhalter [NAME_1] bitte ignorieren."
    )
    fake_entities = [
        {"start": text.index("Dr Nekibe"), "end": text.index("Dr Nekibe") + len("Dr Nekibe"),
         "label": "person", "score": 0.9},
        {"start": text.index("Musterstraße"), "end": text.index("Musterstraße") + len("Musterstraße"),
         "label": "address", "score": 0.9},
        {"start": text.index("12345 Musterstadt"), "end": text.index("12345 Musterstadt") + len("12345 Musterstadt"),
         "label": "address", "score": 0.9},
    ]

    def run_pipeline(fixes):
        spans = detect_structured(text, fixes=fixes)
        for ent in fake_entities:
            s, e = ent["start"], ent["end"]
            if ent["label"] == "person":
                s, e = trim_person_title(text, s, e)
            spans.append((s, e, ent["label"]))
        spans = suppress_placeholder_spans(text, spans)
        spans = apply_address_fixes(text, spans, fixes=fixes)
        return sorted(merge(spans), key=lambda s: -s[0])

    fixes_off_result = run_pipeline(frozenset())

    iban_str = "DE89370400440532013000"
    expected = sorted(
        [
            [text.index(iban_str), text.index(iban_str) + len(iban_str), "iban"],
            [text.index("Musterstraße"), text.index("Musterstraße") + len("Musterstraße"), "address"],
            [text.index("12345 Musterstadt"), text.index("12345 Musterstadt") + len("12345 Musterstadt"), "address"],
            [text.index("Nekibe"), text.index("Nekibe") + len("Nekibe"), "person"],
        ],
        key=lambda s: -s[0],
    )
    assert fixes_off_result == expected

    # and contrast with fixes ON, to prove the "off" fixture actually
    # exercises all four toggles (i.e. this isn't a vacuously-passing test)
    fixes_on_result = run_pipeline({"chain", "housenum", "dobslash", "spacedemail"})
    on_texts = {text[s:e] for s, e, _ in fixes_on_result}
    assert "Musterstraße 12, 12345 Musterstadt" in on_texts  # chain+housenum fired
    assert "Juni / 36" in on_texts                            # dobslash fired
    assert "j . doe @ web . de" in on_texts                   # spacedemail fired
    assert on_texts != {text[s:e] for s, e, _ in fixes_off_result}


# Spaced phone formats

def test_phonespace_detects_spaced_paren_forms():
    for t in ["( 173 ) - 2187318", "( 675 ) - 7511209",
              "( 54 ) . 7788 . 1346", "( 19 ) 3465 . 8334",
              "( 818 ) . 5441266"]:
        text = f"Erreichbar unter {t} tagsüber."
        spans = [text[s:e] for s, e, l in detect_structured(text) if l == "phone number"]
        assert spans == [t], t


def test_phonespace_detects_spaced_plus_forms():
    # asserted POST-merge: PHONE_RE's domestic branch may also emit the
    # digit tail ("0672166 4816"); merge()'s longer-span rule must leave
    # exactly the full "+ ..." span (the shipped pipeline always merges).
    for t in ["+ 0672166 4816", "+ 09-514863701", "+ 04 64-442-0454",
              "+ 02 . 48 . 431-1974", "+ 08 417549862"]:
        text = f"Notfallkontakt: {t} (Zentrale)."
        spans = [text[s:e] for s, e, l in merge(detect_structured(text)) if l == "phone number"]
        assert spans == [t], t


def test_phonespace_bare_groups_require_cue():
    # with a phone cue in the preceding 40 chars: match
    text = "Telefonnummer im格式: 7631 . 204-4963 hinterlegt."
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "phone number"]
    assert "7631 . 204-4963" in spans
    # same digits with NO cue: no match (order-number safety)
    text2 = "Bestellung erfasst als 7631 . 204-4963 im System."
    spans2 = [text2[s:e] for s, e, l in detect_structured(text2) if l == "phone number"]
    assert spans2 == []


def test_phonespace_bare_pure_space_groups_with_cue():
    text = "Rückruf bitte an 4703 508 2873 heute Abend."
    spans = [text[s:e] for s, e, l in detect_structured(text) if l == "phone number"]
    assert "4703 508 2873" in spans


def test_phonespace_rejects_spaced_money_amounts():
    # plus branch guard: spaced amounts must not match ("+ 5 000 000 Euro")
    text = "Wir suchen eine Finanzierung von + 5 000 000 Euro für das Projekt."
    spans = [l for _, _, l in detect_structured(text) if l == "phone number"]
    assert spans == []


def test_phonespace_does_not_swallow_credit_card_as_three_groups():
    # 16-digit CC in 4 groups: a bare-branch candidate can start mid-number
    # ("7375 8689 9855"), but POST-merge the longer Luhn credit-card span
    # must own the whole number and no phone span may survive inside it.
    text = "Rufnummer folgt. Karte: 4556 7375 8689 9855 gültig bis 12/27."
    merged = merge(detect_structured(text))
    phone = [text[s:e] for s, e, l in merged if l == "phone number"]
    assert all("7375" not in p for p in phone)
    assert any(l == "credit card" and "4556" in text[s:e] for s, e, l in merged)


def test_phonespace_does_not_match_clock_time_or_dates():
    text = "Termin um 2:30 Uhr am 14.06.1987 im Büro."
    spans = [l for _, _, l in detect_structured(text) if l == "phone number"]
    assert spans == []


def test_phonespace_off_when_fix_toggled_off():
    text = "Erreichbar unter ( 173 ) - 2187318 tagsüber."
    spans = [l for _, _, l in detect_structured(text, fixes=frozenset()) if l == "phone number"]
    assert spans == []
    spans2 = [l for _, _, l in detect_structured(text, fixes={"housenum", "dobslash"})
              if l == "phone number"]
    assert spans2 == []


def test_phonespace_does_not_span_across_a_line_break():
    # A signature line's leading house number must not join the phone span.
    text = "tel. +44 20 4006 7166\n3 elliot stravenue\nba8v 5zp"
    spans = [text[s:e] for s, e, l in merge(detect_structured(text)) if l == "phone number"]
    assert spans == ["+44 20 4006 7166"]
    text2 = "Tel. + 04 64-442-0454\n7 Musterweg"
    spans2 = [text2[s:e] for s, e, l in merge(detect_structured(text2)) if l == "phone number"]
    assert spans2 == ["+ 04 64-442-0454"]


# --- Cue-gated building-number detection ------------------------------------

def test_building_number_detects_only_explicit_address_fields():
    text = "Gebäudenummer: 988; Bautenummer 857; Hausnummer #12A"
    spans = [text[start:end] for start, end, label in detect_structured(text) if label == "address"]
    assert spans == ["988", "857", "12A"]


def test_building_number_rejects_generic_numbers_and_can_be_disabled():
    text = "Bestellnummer 988 und Gebäudenummer: 857"
    active = [text[start:end] for start, end, label in detect_structured(text) if label == "address"]
    disabled = [text[start:end] for start, end, label in detect_structured(text, fixes=frozenset()) if label == "address"]
    assert active == ["857"]
    assert disabled == []


def test_building_number_handles_html_entities_and_sentence_periods():
    text = "Ihre Geb&auml;udenummer 988. Neue Bautenummer 857."
    spans = [text[start:end] for start, end, label in detect_structured(text) if label == "address"]
    assert spans == ["988", "857"]


# --- Ambiguous month/slash reporting periods ----------------------------------

def test_month_slash_after_a_bare_preposition_is_still_masked():
    # A bare am/bis/ab is too weak a reason to withhold masking. A second,
    # disjoint development set showed that the old rule suppressed genuine DOB
    # spans in deadline-shaped prose. Numeric dates stay recall-first; only an
    # explicit operational date field suppresses now.
    text = "Die Angabe wurde am Juli/19 erfasst."
    dates = [text[start:end] for start, end, label in detect_structured(text) if label == "date of birth"]
    assert dates == ["Juli/19"]


def test_month_slash_after_am_is_retained_with_birth_cue():
    text = "Geboren am Oktober/64."
    dates = [text[start:end] for start, end, label in detect_structured(text) if label == "date of birth"]
    assert dates == ["Oktober/64"]


def test_month_slash_validity_periods_after_bis_or_ab_are_masked_recall_first():
    # Same reversal as above: prepositional context no longer exempts a date.
    text = "Gültig bis Oktober/86 und ab Juli/09."
    dates = [text[start:end] for start, end, label in detect_structured(text) if label == "date of birth"]
    assert dates == ["Oktober/86", "Juli/09"]


def test_month_slash_operational_date_fields_are_not_dobs():
    text = "Termin: Juni/30; Deckungsbeginn: Oktober/21; Geburtsdatum: Juni/35."
    dates = [text[start:end] for start, end, label in detect_structured(text) if label == "date of birth"]
    assert dates == ["Juni/35"]


# --- Phone boundary and IBAN collisions --------------------------------------

def test_phone_detector_rejects_valid_iban_tails_and_long_digit_substrings():
    text = "IBAN CH93 0076 2011 6238 5295 7; Bewertungsparameter 08545982968548529850"
    spans = [(text[start:end], label) for start, end, label in detect_structured(text)]
    assert ("CH93 0076 2011 6238 5295 7", "iban") in spans
    assert not any(label == "phone number" for _, label in spans)
    malformed = "IBAN CH 3653 7482 0883 2024 3"
    assert not any(label == "phone number" for _, _, label in detect_structured(malformed))


def test_phone_detector_rejects_hyphenated_identifier_tail_but_keeps_phone():
    text = "Kennung CHE-080-730-591; Telefon +49 30 1234567"
    phones = [text[start:end] for start, end, label in detect_structured(text) if label == "phone number"]
    assert phones == ["+49 30 1234567"]

# Corpus-style honorifics can appear glued to either edge of a person span.

def test_corpus_title_is_trimmed_from_both_ends():
    text = "Bgm Nolan Berger und Renata Fr sind eingeladen."
    assert text[slice(*trim_person_title(text, 0, 16))] == "Nolan Berger"
    assert text[slice(*trim_person_title(text, 21, 30))] == "Renata"


def test_corpus_title_never_consumes_the_whole_span():
    # A span that is nothing but an honorific must survive unchanged rather than
    # collapse to an empty span (which would drop the mask entirely).
    text = "Bgm meldet sich."
    assert trim_person_title(text, 0, 3) == (0, 3)


def test_corpus_title_leaves_sen_alone_as_a_real_surname():
    # "Sen" is a genuine trailing surname; trimming it would turn a true
    # positive into a leaked gold token. Deliberately not in the trim list.
    text = "Kontakt ist Bo Lin heute."
    assert text[slice(*trim_person_title(text, 12, 18))] == "Bo Lin"


def test_corpus_title_respects_the_fix_toggle(monkeypatch):
    monkeypatch.setenv("NOBODY_PIPELINE_FIXES", "chain,housenum")
    text = "Bgm Nolan Berger kommt."
    assert trim_person_title(text, 0, 16) == (0, 16)


# addrguard: a postal address is not a network address, and a model address span
# must not absorb a checksum-validated structured detection.

def test_addrguard_drops_network_addresses():
    text = "Netzadresse: 24:e1:43:0d:76:a8 und Wallet 0xe9cc55f163ed39097c0c54ac95d0191713b51ab8."
    spans = [(13, 30, "address"), (42, 84, "address")]
    assert apply_address_fixes(text, spans) == []


def test_addrguard_drops_bare_placeholder_tokens():
    text = "Kontaktadresse ist SECONDARYADDRESS_17 ."
    assert apply_address_fixes(text, [(19, 38, "address")]) == []


def test_addrguard_keeps_a_real_address_untouched():
    text = "Anschrift: Blücherstraße 5, 52525 Budenheim."
    assert apply_address_fixes(text, [(11, 43, "address")]) == [(11, 43, "address")]


def test_addrguard_trims_a_swallowed_phone_number():
    text = "Adresse: 2 Kurt-Schumacher-Straße, 99084, 6267-747-1501"
    result = apply_address_fixes(text, [(9, 55, "address"), (42, 55, "phone number")])
    trimmed = [sp for sp in result if sp[2] == "address"]
    assert trimmed == [(9, 40, "address")], trimmed
    assert text[trimmed[0][0]:trimmed[0][1]] == "2 Kurt-Schumacher-Straße, 99084"


def test_addrguard_respects_the_fix_toggle(monkeypatch):
    monkeypatch.setenv("NOBODY_PIPELINE_FIXES", "chain,housenum")
    text = "Netzadresse: 24:e1:43:0d:76:a8 ."
    assert apply_address_fixes(text, [(13, 30, "address")]) == [(13, 30, "address")]


# Separator and morphology variants of German building-number field labels.

def test_building_number_accepts_separator_and_morphology_variants():
    for text, expected in [
        ("Gebäude Nr. 335", ["335"]),
        ("Gebäude-Nr: 12", ["12"]),
        ("Gebäudenr. 7", ["7"]),
        ("Nummer des Gebäudes: 44", ["44"]),
        ("Bau-Nummer: 169", ["169"]),
        ("Haus-Nr. 8", ["8"]),
    ]:
        spans = [text[s:e] for s, e, l in detect_structured(text) if l == "address"]
        assert spans == expected, (text, spans)


def test_building_number_cue_stays_narrow():
    # A generic address field is NOT a building-number cue: it is routinely
    # followed by order, year, room, or phone values rather than house numbers.
    for text in ["Adresse: 361", "Anschrift: 2024", "Telefonnummer: 0301234",
                 "Bestellnummer 988", "Zimmer 13"]:
        spans = [text[s:e] for s, e, l in detect_structured(text) if l == "address"]
        assert spans == [], (text, spans)


def test_addrmerge_joins_fragments_across_address_punctuation():
    # A component-level model emits street and postal city separately; they are
    # one postal address and must be masked as one span.
    text = "Anschrift: Blücherstraße 5, 52525 Budenheim."
    merged = [sp for sp in apply_address_fixes(text, [(11, 27, "address"), (29, 43, "address")])
              if sp[2] == "address"]
    assert merged == [(11, 43, "address")]
    assert text[merged[0][0]:merged[0][1]] == "Blücherstraße 5, 52525 Budenheim"


def test_addrmerge_does_not_join_across_real_text():
    # More than a short punctuation run between fragments means two addresses.
    text = "Werk in Essen und Lager in 12345 Hamburg."
    spans = [(8, 13, "address"), (27, 40, "address")]
    assert sorted(sp for sp in apply_address_fixes(text, spans) if sp[2] == "address") == spans
