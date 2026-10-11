# Carrowmore Array O&M assessment

> All people, employers, records and events in this project are synthetic. The data was supplied for a Pearson job-application assessment; this is not a real employment decision system.

This repository answers one bounded question: **which current keepers in the permitted 40-profile subset could plausibly interview for Carrowmore Array Operations & Maintenance, and what would each need first?** It evaluates 38 current keepers. K1203 and K1458 are retained as traceable historical records but explicitly excluded from the current redeployment cohort.

The submitted scenario date is **2026-10-11**. The evaluator requires `--as-of`; it never substitutes the computer clock. It reads the supplied ZIP directly and does not require SQL, a trained model, network access, or third-party Python packages. The completed personal classification lab and SQL mirror are outside this repository and are not read or changed.

## Result

The bounded run produced:

| Result | Profiles |
|---|---:|
| Supported technical interview | 22 |
| Targeted screening first | 16 |
| Insufficient evidence | 0 |
| Leaver outside the current cohort | 2 |

The result is not a ranking and no target count was used. A supported result means the records justify a structured technical interview. A targeted-screening result means relevant evidence exists, but sparse/repetitive logs or a recent explicit role-related appraisal concern must be tested before deciding on a full technical interview. It remains deliberately conservative about eligibility and mobilisation: **no profile is declared competent, authorised, fully eligible, or mobilisation-ready.** Medical fitness, current safety coverage, willingness to work at height/on vessels, and employer practical assessment remain explicit checks.

The readable answer is [output/recommendations.md](output/recommendations.md). The machine-readable answer, including exact cited text, source references, dated credential claims, conflicts, future evidence and next actions, is [output/recommendations.json](output/recommendations.json). The independent test result is [output/qa_report.json](output/qa_report.json).

## Run it

Requirements:

- Python 3.12 (standard library only; the verified run used Python 3.12.13 from `carrowmore-ml`)
- the unmodified `carrowmore-data-pack.zip`

From this repository, in the current assessment workspace:

```powershell
& 'C:\Users\George\.conda\envs\carrowmore-ml\python.exe' src\array_om_evaluator.py `
  --source-zip ..\data\carrowmore-data-pack.zip `
  --as-of 2026-10-11 `
  --output-dir output
```

Portable equivalent on any platform with Python on `PATH`:

```sh
python src/array_om_evaluator.py \
  --source-zip /path/to/carrowmore-data-pack.zip \
  --as-of 2026-10-11 \
  --output-dir output
```

The program verifies the archive SHA-256, 1,447-member inventory, and every selected member fingerprint before producing output. A missing or malformed `--as-of` is an error.

Run independent QA separately after generation:

```powershell
& 'C:\Users\George\.conda\envs\carrowmore-ml\python.exe' qa\independent_qa.py `
  --source-zip ..\data\carrowmore-data-pack.zip `
  --results output\recommendations.json `
  --report output\qa_report.json
```

The submitted repaired-package QA run passed **4,777/4,777 checks**, including the ten cases defined before implementation, the earlier correction areas, and direct checks that every retained experience row renders in its own Markdown profile, measurement-unit variants share a canonical pattern, K1200 display exceptions do not inflate diversity, missing dated-Pass actions verify before prescribing training, and the named appraisal excerpts remain exact. The QA program reads the ZIP and output directly and never imports the evaluator or recomputes its recommendation policy.

## What the output means

Each profile keeps these concepts separate:

- `interview_recommendation`: whether the bounded records justify a conversation;
- `recommendation_reason` and `recommendation_criteria`: person-specific cited reasons and the non-ranking rule result;
- `work_history_review`: proof that the complete clean history was reviewed, with row counts, cutoff handling and template-collapsed diversity;
- `relevant_experience`: exact clean log text, date, entry ID, raw source reference, identity provenance, raw corroboration and measurement warnings;
- `appraisal_review`: every exact keeper-code-keyed appraisal ID reviewed, role-relevant exact excerpts and source-text hashes, with null-key/name-only rows deliberately unattached;
- `application_eligibility`: whether the supplied evidence establishes the posting's application position;
- `mobilisation_readiness`: whether every safety, medical and employer gate is established;
- `credential_claims`: dated LearnHub rows with Pass, Attended and Not achieved preserved exactly;
- `credential_conflicts`: claims that need evidence, without converting missing records into accusations;
- `future_evidence_not_used`: records later than the scenario cutoff;
- `initial_selection_actions`: the interview or screening step now;
- `later_qualification_and_mobilisation_actions`: credential, medical and employer gates only if selection supports progression.

The evaluator reviews every clean log row for every profile. The normal evidence rule requires an explicit maintenance action plus an electrical or mechanical plant term. Superficial numeric, measurement-value/unit and template variants are collapsed, and up to five strong examples are shown. All four named K1200 records remain visible, but their IDs are display exceptions rather than separate pattern identities; K1200 therefore has three canonical decision patterns, not seven. Counts, hours, grade and tags are never treated as competence. Five or more distinct patterns with no explicit role-related concern in the previous ten years support a technical interview; sparse evidence or such a concern routes to targeted screening. Fewer than three distinct patterns without strong keyed manager testimony is insufficient. These are transparent gates, not a score or ranking.

The previously omitted `raw/appraisals/appraisals.jsonl` is now part of the verified input contract (SHA-256 `c19ba6216619c0c4d103b5dd7d99edb49f9722fba94a6eb9de824adfba1488d1`). It contains 4,422 rows: 2,694 have a keeper code, 1,728 do not, and 305 are exactly keyed to 37 current profiles. Only exact `keeper_code` joins are allowed; null-key/name-only records are not guessed. All 305 are reviewed. Rows outside the narrow excerpt selector are labelled **not selected by the appraisal filter**, not declared irrelevant. The selected context now expressly includes K0147/AP000090's positive rope-work testimony and K0354/AP000752/AP000753's reporting concerns; those excerpts do not independently promote or reject either person. Full source-text hashes make excerpts checkable without reproducing unmatched narrative. Appraisal years remain year precision: 2026 records are context-only because their position relative to 2026-10-11 is unknown.

K1200 illustrates the corrected decision contract. CL005994, CL007505, CL009097 and CL009921 record hands-on activity, but AP003496 explicitly disputes the depth behind the course/log record. Neither source silently wins, so the immediate disposition is `targeted_screening_first`. The same concern policy is applied across all profiles. K0371 and K0847 also illustrate the distinction between repetitive activity records and stronger keeper-code-keyed manager testimony; that testimony supports interview questions but is not competence or authorisation.

Credential status preserves each supplied LearnHub outcome and expiry. The output separately calculates the nominal date implied by the scheme's stated renewal years. If those two dates produce different status at the cutoff, the claim is marked unresolved and issuer verification is required; neither date silently wins. `Pass`, `Attended`, and `Not achieved` remain different. WAHS-1 is mapped to the posting's height requirement as an explicit prototype interpretation because the supplied OSSC definition does not include height.

Identity provenance distinguishes raw keeper codes, payroll references, names and absent identifiers. Integer-like payroll values are normalized across leading-zero, decimal and scientific notation without adding digits; for example, raw `1.1245E+04` corroborates K0147's clean `0011245`. Conflicting identifiers remain visible and clean/manual attribution remains explicit. Era-3 CSV row numbers include the header; era-2 citations use file plus record ID; era-1 citations use physical lines.

Quoted measurement anomalies are retained verbatim and flagged. Megger readings in `psi`/`bar`, pump delivery in volts and AVR voltage settings in ohms support only that an activity was recorded; their numerical measurements are not treated as reliable and no repair is invented.

For current profiles, selection happens first. Only after a positive selection outcome do later actions proceed through issuer/source verification, willingness and working-condition confirmation, medical clearance, module-specific OSSC work, dependent WAHS work, and employer permit/practical assessment. Each module action distinguishes a current Pass, expired Pass, Attended, Not achieved, conflict or missing evidence. An absent matched dated Pass now requires verification of any existing certificate first; training or assessment is conditional on coverage remaining unestablished. The posting's promise to fund renewals is reported only for renewals. The two leavers receive no training or mobilisation pathway.

The bounded defect repair reduced canonical-pattern counts for 15 profiles (K0303, K0371, K0482, K0561, K0592, K0650, K0847, K0897, K1200, K1231, K1302, K1458, K1468, K1511 and K1538). No profile crossed an existing decision gate, so the 22 supported / 16 targeted / 0 insufficient / 2 outside-cohort totals did not change. This was observed, not forced.

## Repository layout

```text
SOURCE_FINGERPRINTS.json       verified assessment and selected-source hashes
src/array_om_evaluator.py      deterministic file-based evaluator
qa/independent_qa.py           independent source/output and ten-case checks
output/recommendations.json    complete structured answer
output/recommendations.md      readable candidate-by-candidate answer
output/qa_report.json          detailed QA evidence
output/run_metadata.json       interpreter, commands, repeatability and hashes
WRITTEN_EXPLANATION.md         scope, AI corrections and production reflection
```

The source archive is not duplicated inside this repository. Supply its path with `--source-zip`; the required hash is recorded in `SOURCE_FINGERPRINTS.json` and enforced in code.

## Known limits

- This is a deliberately permitted 40-profile slice, not a ranking of all 340 current personnel in the source pack and not the separate 240-example ML mirror.
- Older name-only training is not guessed into identities. Clean aggregate certification summaries remain claims rather than independent issuer verification.
- Exact course availability, duration, price and fastest completion route are not in the sources and remain unknown.
- Work narratives support interview questions. They do not establish assessed competence, an appointment, current authorisation, or qualifying experience duration.
- Appraisals are manager testimony, sometimes internally conflicting and sometimes templated. They can define screening questions but do not establish competence or current authorisation.
- Oileann/K1538's manager testimony remains an interview lead, but its claimed eleven-year Nevisbeg tenure conflicts with the recorded 1998 joining date and Nevisbeg posting beginning in 2009.
- Unicode is preserved from the source. Where the supplied pack itself contains a replacement character, the JSON retains it and the readable report uses the supplied ASCII name where available.

See [WRITTEN_EXPLANATION.md](WRITTEN_EXPLANATION.md) for the required design reflection and effort statement.
