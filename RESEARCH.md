# Research record

This document records the seven research loops behind `nobody` v0.3.0. It is a
compact public account, not a reconstruction of private orchestration logs. Raw
benchmark documents and leak excerpts are deliberately excluded.

## Reading the numbers

- **F1** is micro-averaged exact token-span F1. A semantically correct entity
  with a different boundary is scored as wrong.
- **Token leakage** is the share of gold PII tokens not covered by any predicted
  PII span. Lower is better and, for release decisions, takes precedence over
  F1.
- Loops 2–3 used the original German canonical set. Protocol v2 begins at loop
  4, so only loop 4 onward is directly comparable on the same 3,000-document
  German set.
- All evaluated corpora are described by their publishers as synthetic. No
  result below establishes performance on real personal records.

## Seven-loop overview

| loop | central question | best canonical outcome | decision |
|---|---|---|---|
| 1 | Can a bounded synthetic fine-tune improve the GLiNER baseline without overfitting? | exploratory candidates reached strong in-distribution scores but poor German transfer | no release |
| 2 | Can target-shaped synthetic data and deterministic replay satisfy the first release gates? | release line 0.662 F1 / 1.74% leakage; research line 0.700 / 2.40% on the original German set | first gate-passing release line retained |
| 3 | Do full-epoch training, OpenPII data, or weight interpolation close the German gap? | research mix 0.783 / 2.67%; synthetic-only interpolation 0.708 / 2.40% | both failed G2; no replacement |
| 4 | Can a corrected, larger protocol and a licensed mixed corpus produce a stable release? | 0.791 [0.776, 0.805] / 1.63% [1.17, 2.17] on protocol v2 | v0.2.0 shipped |
| 5 | Can address, date, and phone coverage beat the matched Piiranha baseline while staying below 2% leakage? | 0.799 [0.784, 0.814] / 2.05% [1.48, 2.67] | G2 failed by 0.049pp; frozen failure |
| 6 | Do component-shaped address data, person routing, or model ensembles transfer? | highest-F1 ensemble 0.815 [0.800, 0.829] / 2.61%; single-model champion 0.801 / 2.05% | every candidate failed G2 |
| 7 | Was the model wrong, or was the development instrument blind to the remaining leaks? | 0.795 [0.780, 0.810] / 1.51% [1.079, 1.995] | all gates pass; v0.3.0 |

## Loop 1 — establish the instrument

The first loop built the evaluator, deterministic/model pipeline, synthetic
corpus, and bounded MPS training harness. Short candidates improved the
in-distribution synthetic metric, but the better synthetic score did not
transfer to the external German distribution. A 600-second candidate reached
0.922 synthetic F1 while remaining below 0.46 F1 on the early external German
check.

**Finding:** in-distribution synthetic optimization was not a valid selection
objective for German generalization. The release process needed a disjoint
German development instrument and an explicit leakage metric.

## Loop 2 — target data and replay

The second loop added German target-shaped synthetic documents and deterministic
replay examples. The synthetic-only release line reached 0.662 F1 at 1.74%
leakage on the original German canonical set, satisfying the initial gates. A
research line reached 0.700 F1 but leaked 2.40% and was not eligible.

**Finding:** data distribution mattered more than a small hyperparameter search.
The loop also established the rule that a higher F1 candidate does not replace a
lower-leakage release when the candidate fails the budget.

## Loop 3 — full epochs, licensed data, and interpolation

Three hypotheses were tested:

1. **More synthetic training.** Full-epoch training improved person precision
   but worsened address recall; trainer loss did not identify the external-data
   optimum.
2. **A permissively licensed mixed corpus.** German rows from OpenPII-1M
   (CC-BY-4.0) substantially improved address recall. The research checkpoint
   reached 0.783 F1 but 2.67% leakage, so it failed G2.
3. **WiSE-FT interpolation.** Interpolating two synthetic-only checkpoints
   reached 0.708 F1 but 2.40% leakage, another G2 failure.

The OpenPII candidates were checked against protected evaluation candidates with
exact-text and near-duplicate controls before use. The planted controls fired;
no PII-bearing exact or near duplicate was found.

**Finding:** additional data closed much of the F1 gap, especially on addresses,
but recall-side leakage was nearly flat across a large threshold grid. The
remaining errors were coverage errors, not a threshold-tuning problem.

## Loop 4 — protocol v2 and v0.2.0

Protocol v2 replaced the small, noisy German gate with 3,000 documents and
predeclared three release gates:

- **G1:** German F1 at least 0.05 above the matched zero-shot baseline;
- **G2:** token leakage no higher than 2.00% on both German and synthetic sets;
- **G3:** minimum F1 across the two sets at least 0.55.

A 38,581-instance licensed mix was trained from the pinned Apache-2.0 GLiNER
base. Checkpoint 800 was selected on development data before the canonical look.
It reached 0.791 F1 / 1.63% leakage on German protocol v2 and 0.927 / 0.51% on
the multilingual synthetic regression set. That configuration became v0.2.0.

**Finding:** the composition of the mixed corpus, not more epochs, was the useful
lever. The leakage point estimate passed, but its 95% upper bound remained above
2%, leaving little safety margin.

## Loop 5 — deterministic coverage and a frozen near miss

Loop 5 first remeasured Piiranha under the same deterministic pipeline, label
mapping, and fixed threshold rule. Candidate work then targeted observed
development errors:

**Kept on development data**

- cue-gated German building and house-number fields;
- HTML-entity and sentence-punctuation variants;
- narrow month/slash date exclusions for explicit operational fields;
- phone guards against IBAN-like, credit-card, hyphenated-ID, and long-number
  collisions.

**Rejected before the canonical look**

- broad street-suffix heuristics (no measurable improvement);
- broad DOB birth-cue gates (leakage exceeded 2%);
- continued address training (F1 regressed despite lower leakage);
- threshold exceptions (the measured frontier was flat).

The frozen finalist improved F1 to 0.799 but leaked 2.049%, failing G2 by
0.049 percentage points. It was reported as a failure and not tuned again from
that canonical batch.

**Finding:** a close point estimate is still a failed gate. Address leakage was
structural, while some precision-oriented date rules hid leakage that the first
development set did not contain.

## Loop 6 — synthetic address quality, routing, and ensembles

The synthetic-data audit found a concrete annotation mismatch: protocol-v2
German address gold was mostly single-token component spans, including bare
house numbers and place fragments, while the generated training corpus mostly
supervised full postal-address blocks. A contamination-clean component-address
wave was built to mirror the development shape distribution.

Tested hypotheses included:

- component-level address data and number hard negatives;
- address-prior rebalancing and rehearsal mixes;
- corpus-title trimming and non-postal address guards;
- label routing between the champion and new checkpoints;
- two-model and three-model person/address voting;
- address-prompt variants and component-span merging.

The component-trained models reduced address leakage, but their exact-span
precision collapsed and total F1 fell. Conservative address merging recovered
only 0.001 F1 on the champion and did not rescue the component models. The best
person-routing ensemble reached 0.815 F1 but raised person leakage enough to
push total leakage to 2.61%. Every candidate failed G2.

Loop 6 originally compared overlapping marginal confidence intervals. Loop 7
corrected the statistical method to paired document-level bootstrap differences;
no release claim relies on the earlier marginal-CI interpretation.

**Finding:** training and ensembles were expensive, but the main blocker was not
model capacity. It was calibration of the development instrument and annotation
conventions.

## Loop 7 — fix the instrument, then the pipeline

A second 3,000-document development stream was constructed from an untouched
slice with the same mapper, negative-document population, and label distribution
as the canonical set. Determinism and overlap checks were performed before it
was used. The original development set had reported zero DOB leakage and
substantially understated phone leakage; the second instrument exposed both on
its first run.

Four deterministic changes were selected on that development stream:

- additional separator and morphology variants for explicit building-number
  fields, while rejecting generic `Adresse`, room, order, and telephone fields;
- removal of the loop-5 `am/bis/ab` month/slash exemption, restoring the
  documented recall-first date policy;
- optional spaces around phone separators plus German contact lead-ins;
- normalization of adjacent address components across short postal punctuation.

The model weights and production thresholds did not change. Threshold Pareto
replicates moved F1 by at most 0.001 and leakage by about 0.3pp across the entire
measured grid, confirming that threshold tuning was not a useful lever.

### Frozen canonical result

| set | F1 [95% CI] | token leakage [95% CI] |
|---|---:|---:|
| German protocol v2 | 0.795 [0.780, 0.810] | 1.51% [1.079%, 1.995%] |
| multilingual synthetic regression | 0.927 | 0.51% |

Against the loop-6 single-model champion at identical weights:

- paired ΔF1: **−0.0064** [−0.0097, −0.0034];
- paired Δleakage: **−0.54pp** [−0.96, −0.20].

Both effects exclude zero. A small, real F1 loss bought a larger, real leakage
reduction. The stricter leakage-CI bar passed by only 0.005pp, with
`P(leakage ≤ 2.0%) = 0.976`; this is a pass, not a comfortable margin.

### Comparator result

Under the same current pipeline, Piiranha scored 0.840 F1 / 0.93% leakage on its
400k home release. The paired difference was −0.0452 F1
[−0.0586, −0.0318] and +0.58pp leakage [+0.11, +1.09] against `nobody`.
`nobody` did not beat Piiranha there.

On a contamination-filtered OpenPII-1M German validation sample, the ranking
reversed: `nobody` 0.982 versus Piiranha 0.915, paired ΔF1 +0.0667
[+0.0593, +0.0741]. That is not a universal win: it is `nobody`'s home release,
it has no DOB class, and its address boundaries differ. The ≈0.105 interaction
between the two benchmarks is the scientific finding: exact-span scores on
synthetic PII data are strongly shaped by the generator and annotation scheme.

## Release gates

| gate | v0.3.0 value | verdict |
|---|---:|---|
| G1: German F1 ≥ 0.635 + 0.05 | 0.795 | pass |
| G2: German / synthetic leakage ≤2.00% | 1.51% / 0.51% | pass |
| loop-7 stricter G2: German CI upper bound <2.00% | 1.995% | pass by 0.005pp |
| G3: min(German, synthetic F1) ≥0.55 | 0.795 | pass |

## Privacy, provenance, and publication boundary

- Released weights contain no training rows from the evaluation-only 400k
  benchmark.
- The model training mix is 74% German OpenPII-1M rows under CC-BY-4.0 and 26%
  companion procedurally generated documents under Apache-2.0.
- The base model and released weights are Apache-2.0. Piiranha is used only as a
  CC-BY-NC-ND research comparator.
- Raw benchmark documents, false-positive/false-negative excerpts, local file
  paths, credentials, chat identifiers, and source redaction logs are excluded
  from Git and release artifacts.
- Public tests use invented or format-only fixtures. Treat any documents and
  redaction logs processed in production as sensitive data.
