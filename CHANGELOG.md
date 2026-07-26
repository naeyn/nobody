# Changelog

All notable public changes are recorded here. The model weights are distributed
from [Hugging Face](https://huggingface.co/naeyn/nobody-pii-de); source releases
are published on [GitHub](https://github.com/naeyn/nobody/releases).

## [0.3.0] — 2026-07-26

### Changed

- Reduced German protocol-v2 token leakage from the loop-6 champion's 2.05% to
  **1.51%** while retaining 0.795 F1. The paired change is −0.54 percentage
  points leakage [−0.96, −0.20] and −0.0064 F1 [−0.0097, −0.0034].
- Expanded cue-gated building-number detection to German separator and
  morphology variants such as `Gebäude-Nr.`, `Gebäudenr.`, `Bau-Nummer`, and
  `Haus-Nr.`. Generic address, room, order, and phone fields remain excluded.
- Restored recall-first handling of month/slash dates after weak prepositions.
  Explicit operational fields such as appointment, coverage-start, and report
  dates remain excluded.
- Added spaced/punctuated phone formats and German contact lead-ins while
  retaining guards for monetary amounts, times, line breaks, IBAN-like values,
  credit cards, hyphenated identifiers, and long digit runs.
- Trimmed corpus-style honorifics from person boundaries without dropping spans
  consisting only of an honorific.
- Rejected non-postal model addresses such as network identifiers and generated
  placeholder tokens; trimmed structured phone tails from postal-address spans.
- Normalized adjacent address components separated only by short postal
  punctuation.

### Research and reporting

- Added a seven-loop public research record with accepted and rejected
  hypotheses, fixed gates, contamination controls, and paired bootstrap results.
- Corrected loop comparisons to paired document-level bootstrap differences
  (10,000 resamples) rather than overlapping marginal confidence intervals.
- Added a contamination-filtered CC-BY-4.0 OpenPII-1M comparison. The ranking
  reversal across two synthetic releases is reported as a generator/annotation
  interaction, not a universal model win.
- Added generated light/dark seven-loop graphics.
- Removed raw examples, local paths, credentials, restricted benchmark records,
  and private orchestration from the public release boundary.
- Expanded the public behavior suite from 89 to 111 tests.
- Pinned `multiprocess==0.70.17` to avoid a Python 3.12 resource-tracker traceback during otherwise successful CLI shutdown.

### Model artifact

- **No binary weight change.** `model.safetensors`, tokenizer, and GLiNER
  configuration are byte-for-byte unchanged from v0.2.0. v0.3.0 is a source and
  production-policy release.
- Updated the Hugging Face model card with current pipeline metrics, version
  identity, methodology, intended uses, limitations, and provenance.

## [0.2.0] — 2026-07-19

- First public German-first redaction pipeline and Hugging Face model artifact.
- Mixed GLiNER checkpoint trained from a pinned Apache-2.0 base on 25,909 German
  OpenPII-1M rows plus 12,672 companion synthetic instances.
- Deterministic checksum validation for IBAN, credit cards, German tax IDs, and
  Dutch BSNs; format-aware email, phone, license-plate, and numeric-date rules.
- Protocol-v2 German result: 0.791 F1 / 1.63% token leakage.
- Multilingual synthetic regression result: 0.927 F1 / 0.51% token leakage.

[0.3.0]: https://github.com/naeyn/nobody/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/naeyn/nobody/releases/tag/v0.2.0
