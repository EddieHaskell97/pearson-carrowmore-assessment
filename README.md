# Carrowmore Array O&M assessment

> All people, employers, records and events in this project are synthetic. The data was supplied for a Pearson job-application assessment; this is not a real employment decision system.

This repository answers one bounded question: **which current keepers in the permitted 40-profile subset could plausibly interview for Carrowmore Array Operations & Maintenance, and what would each need first?** It evaluates 38 current keepers. K1203 and K1458 are retained as traceable historical records but explicitly excluded from the current redeployment cohort.

The submitted scenario date is **2026-10-11**. The evaluator requires `--as-of`; it never substitutes the computer clock. It reads the supplied ZIP directly and does not require SQL, a trained model, network access, or third-party Python packages. The completed personal classification lab and SQL mirror are outside this repository and are not read or changed.

## Result

The bounded run produced:

| Result | Profiles |
|---|---:|
| Recommend interview | 38 |
| Consider interview | 0 |
| Insufficient relevant evidence in this subset | 0 |
| Leaver outside the current cohort | 2 |

The result is deliberately generous at the interview stage because the posting says the employer would rather train suitable people than screen only for existing certificates. It is deliberately conservative about eligibility and mobilisation: **no profile is declared competent, authorised, fully eligible, or mobilisation-ready.** Medical fitness, current safety coverage, willingness to work at height/on vessels, and employer practical assessment remain explicit checks.

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

The submitted correction-pass QA run passed **2,844/2,844 checks**, including the ten cases defined before implementation and direct checks for the seven bounded corrections. The QA program reads the ZIP and output directly and never imports the evaluator or recomputes its recommendation score.

## What the output means

Each profile keeps these concepts separate:

- `interview_recommendation`: whether the bounded records justify a conversation;
- `recommendation_reason` and `recommendation_criteria`: person-specific cited reasons and the non-ranking rule result;
- `relevant_experience`: exact clean log text, date, entry ID, raw source reference, identity provenance, raw corroboration and measurement warnings;
- `application_eligibility`: whether the supplied evidence establishes the posting's application position;
- `mobilisation_readiness`: whether every safety, medical and employer gate is established;
- `credential_claims`: dated LearnHub rows with Pass, Attended and Not achieved preserved exactly;
- `credential_conflicts`: claims that need evidence, without converting missing records into accusations;
- `future_evidence_not_used`: records later than the scenario cutoff;
- `remaining_requirements` and `next_actions`: what to verify, renew, train or assess first.

The evidence rule requires an explicit maintenance action plus an electrical or mechanical plant term. Up to five de-duplicated examples are shown. Counts, hours, grade and tags are never treated as competence. A stronger interview recommendation requires at least three examples plus diagnostic or electrical-and-mechanical evidence; it remains a shortlist rule, not a ranking or employment decision. K1200 now meets that same rule because CL005994 records work on motor brushes and a commutator, which is consistently categorized as electro-mechanical wherever that wording appears.

Credential status preserves each supplied LearnHub outcome and expiry. The output separately calculates the nominal date implied by the scheme's stated renewal years. If those two dates produce different status at the cutoff, the claim is marked unresolved and issuer verification is required; neither date silently wins. `Pass`, `Attended`, and `Not achieved` remain different. WAHS-1 is mapped to the posting's height requirement as an explicit prototype interpretation because the supplied OSSC definition does not include height.

Identity provenance distinguishes raw keeper codes, payroll references, names and absent identifiers. Integer-like payroll values are normalized across leading-zero, decimal and scientific notation without adding digits; for example, raw `1.1245E+04` corroborates K0147's clean `0011245`. Conflicting identifiers remain visible and clean/manual attribution remains explicit. Era-3 CSV row numbers include the header; era-2 citations use file plus record ID; era-1 citations use physical lines.

Quoted measurement anomalies are retained verbatim and flagged. Megger readings in `psi`/`bar`, pump delivery in volts and AVR voltage settings in ohms support only that an activity was recorded; their numerical measurements are not treated as reliable and no repair is invented.

For current profiles, next actions are ordered: issuer/source verification, willingness and working-condition confirmation, medical clearance, OSSC work, dependent WAHS work, then technical/practical assessment. The posting's promise to fund renewals is reported only for renewals. The two leavers receive no training or mobilisation pathway.

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
- Oileann/K1538's manager testimony remains an interview lead, but its claimed eleven-year Nevisbeg tenure conflicts with the recorded 1998 joining date and Nevisbeg posting beginning in 2009.
- Unicode is preserved from the source. Where the supplied pack itself contains a replacement character, the JSON retains it and the readable report uses the supplied ASCII name where available.

See [WRITTEN_EXPLANATION.md](WRITTEN_EXPLANATION.md) for the required design reflection and effort statement.
