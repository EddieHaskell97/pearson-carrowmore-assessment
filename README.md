# Carrowmore Array O&M assessment

> All people, employers, records and events in this project are synthetic. The supplied records are assessment material, not a real employment decision system.

## The answer

**37 of the 38 current keepers in the permitted subset have specific, attributed maintenance evidence supporting a technical interview. One needs targeted evidence clarification first.** The two leavers are outside the current redeployment cohort. The useful answer is not the high interview percentage by itself: it is the person-specific evidence, uncertainty, interview probe and next task in the generated [redeployment decision brief](output/decision_brief.md).

| Result | Profiles | Immediate next step |
|---|---:|---|
| Supported technical interview | 37 | Test the cited hands-on experience with the person-specific probe |
| Targeted screening first | 1 | Clarify a material contradiction about the core experience claim |
| Insufficient evidence | 0 | No profile in this subset received this outcome |
| Leaver outside the current cohort | 2 | No selection or mobilisation pathway proposed |

The O&M posting accepts hands-on mechanical **or** electrical maintenance experience. It does not require both, a degree, or previous wind work. Accordingly, support means a reason to interview, not a ranking, proof of competence or permission to mobilise. No numerical quota, minimum pattern count or automatic adverse-appraisal veto determines the result.

The two most important reviewed cases illustrate different actions rather than a quota:

| Keeper | Evidence decision and immediate action |
|---|---|
| K0478 | Corroborated electrical maintenance supports interview. Retain the mixed work-quality/checking testimony in AP001159, AP001160, AP001161, AP001162, AP001165 and time-uncertain AP001167; use it for concrete isolation, proving-dead, checking and quality questions rather than denying an interview or inferring current HV authorisation. |
| K1200 | CL005994, CL007505 and CL009097 are qualifying work examples. CL009921 is displayed context only and gains no silent mechanical category. AP003496 directly disputes the personal plant work suggested by the records, so clarify what K1200 performed before technical interview. |

For everyone who progresses, **verify existing credentials and disputed records before prescribing courses**. Then confirm working conditions and willingness, medical fitness, required safety coverage and employer-specific assessment or authorisation. Missing evidence is a verification task, not proof that a qualification or experience does not exist. No profile is declared fully eligible or mobilisation-ready.

## Reading order

1. Start with the generated [redeployment decision brief](output/decision_brief.md). It gives the boundary, cohort work queues, one stable row per current keeper, four contrasting cases and the issuer-verification opportunity.
2. Read [WRITTEN_EXPLANATION.md](WRITTEN_EXPLANATION.md) for the scope choices, AI corrections, production tradeoffs and historical effort statement.
3. Use the [detailed recommendations](output/recommendations.md#current-keeper-comparison) as the evidence appendix when inspecting a claim. It retains exact quotations, dates, source references, conflicts and ordered actions.
4. Use [recommendations.json](output/recommendations.json) for the complete structured answer, or [qa_report.json](output/qa_report.json) for the independent source/output assertions. Run instructions follow below.

I selected the expressly permitted 40-profile clean subset to spend the bounded effort on defensible answers rather than full-population identity repair. The clean layer is a starting point, not ground truth: material claims are checked against detailed training, appraisals, personnel dates and selected raw work evidence. This is not a ranking of all 340 current personnel.

The reference scenario date is **2026-10-11**. The evaluator requires `--as-of`; it never substitutes the computer clock. It reads the supplied ZIP directly and needs only Python's standard library. The separate personal ML/SQL exercise is not a runtime dependency and did not determine these recommendations.

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

Run the alternate-date regression and independent QA separately after final generation:

```powershell
$alternateCheck = Join-Path $env:TEMP 'carrowmore-assessment-alt-20230101'
& 'C:\Users\George\.conda\envs\carrowmore-ml\python.exe' src\array_om_evaluator.py `
  --source-zip ..\data\carrowmore-data-pack.zip `
  --as-of 2023-01-01 `
  --output-dir $alternateCheck

& 'C:\Users\George\.conda\envs\carrowmore-ml\python.exe' qa\independent_qa.py `
  --source-zip ..\data\carrowmore-data-pack.zip `
  --results output\recommendations.json `
  --alternate-results "$alternateCheck\recommendations.json" `
  --report output\qa_report.json

Remove-Item -LiteralPath $alternateCheck -Recurse -Force
```

The verified package QA run passed **8,724/8,724 source/output assertions**, including the ten cases defined before implementation, the earlier correction areas, exact appraisal and station-note passages, cutoff-safe clean/detailed training reconciliation, all 38 rendered navigation targets, source-specific operator questions, every displayed attribution/measurement warning, the source-derived issuer queue, precise personnel chronology, alternate-date regression, faithful UTF-8 Markdown, per-profile evidence rendering, workflow canonicalization and category-to-record citations. These assertions support source fidelity and reproducibility; they are not 8,724 validations of hiring judgments. The QA program reads the ZIP and output directly and never imports the evaluator or recomputes its recommendation policy.

## What the output means

Each profile keeps these concepts separate:

- `interview_recommendation`: whether the bounded records justify a conversation;
- `recommendation_reason` and `recommendation_criteria`: person-specific cited reasons and the non-ranking rule result;
- `work_history_review`: the complete clean history mechanically screened, with row counts, cutoff handling and template-collapsed diversity;
- `relevant_experience`: exact clean log text, date, entry ID, raw source reference, identity provenance, raw corroboration and measurement warnings;
- `experience_category_evidence`: one exact displayed work record supporting every claimed experience category;
- `appraisal_review`: every exact keeper-code-keyed appraisal ID mechanically processed, plus the bounded AI-assisted technical-topic source review, exact excerpts and source-text hashes; null-key/name-only rows remain unattached;
- `application_eligibility`: whether the supplied evidence establishes the posting's application position;
- `mobilisation_readiness`: whether every safety, medical and employer gate is established;
- `credential_claims`: dated LearnHub rows with Pass, Attended and Not achieved preserved exactly;
- `credential_conflicts`: claims that need evidence, without converting missing records into accusations;
- `future_evidence_not_used`: records later than the scenario cutoff;
- `initial_selection_actions`: the interview or screening step now;
- `later_qualification_and_mobilisation_actions`: credential, medical and employer gates only if selection supports progression.

The operator queue turns those fields into concise work assignments. Each candidate link is generated from the exact detailed-report heading using the rendered GitHub fragment, and independent QA proves that every one resolves to exactly one profile. Questions are selected from the cited activity: electrical isolation, fault diagnosis, testing, control systems, mechanical overhaul, routine service or other bounded maintenance. The adjacent evidence-quality column identifies every cited record as raw-identity corroborated, clean/manual attribution without a raw identifier, or a raw-identity conflict, and flags anomalous measurements verbatim for clarification. These warnings do not change the interview decision automatically.

The evaluator reviews every clean log row for every profile. Its extractor looks for an explicit maintenance action plus an electrical or mechanical plant term. Superficial numeric, measurement-value/unit, and equivalent `permit` / `PTW` / `permit bk.` transformer-isolation variants are collapsed only for a descriptive workflow count; original events and citations remain unchanged. The strongest examples plus at least one exact record for every claimed category are displayed. All four named K1200 records remain visible, while their display exceptions do not create extra pattern identities. Counts, dates and canonical workflows describe the bounded evidence but do not decide interview support. Hours, grade and tags are never treated as competence. There is no minimum pattern count, recency cutoff, confidence score, keyword veto or automatic adverse-appraisal window.

The previously omitted `raw/appraisals/appraisals.jsonl` is part of the verified input contract (SHA-256 `c19ba6216619c0c4d103b5dd7d99edb49f9722fba94a6eb9de824adfba1488d1`). It contains 4,422 rows: 2,694 have a keeper code, 1,728 do not, and 305 are exactly keyed to 37 current profiles. Only exact `keeper_code` joins are allowed; null-key/name-only records are not guessed. All 305 rows are mechanically processed; that is not presented as complete semantic human review. A bounded AI-assisted source review of previously unselected technical-topic candidates expanded the exact same-sentence selector. All 180 technical-topic candidate rows are now selected, while the remaining 125 are labelled **not selected by the appraisal filter**, not declared irrelevant. Named repairs include K0478/AP001161, K1231/AP003577, K0847/AP002307 and K0641/AP001695. Positive, adverse, improvement and authorisation context stays together, and year-only 2026 records remain timing-uncertain.

K1200 illustrates the targeted-screen contract. CL005994, CL007505 and CL009097 are qualifying work examples; CL009921 remains visible as material context but gains no derived category and does not count as a qualifying pattern. AP003496 directly disputes whether the suggested plant work was performed personally and records avoided assistance requests, so the discrepancy must be clarified before interview. K0478 is different: CL010541, CL010398 and CL010466 corroborate relevant electrical activity, while the appraisals concern quality, checking and consistency rather than whether all of that activity occurred. The positive 2017 Raheenvarra note is retained but does not prove authorisation. K0478 therefore receives a supported technical interview with exact safety and work-quality questions; K1200 remains the sole targeted screen.

Credential status preserves each supplied LearnHub outcome and expiry. Year-only clean training claims are reconciled against uniquely matching detailed dates before derived module sequences are stated. For K0592, the clean 2026 MECS-5 completion maps to LH500977 on 2026-11-21, so it remains future evidence at the cutoff and is not asserted as established. Independent comparison found 12 clean complete/valid summaries whose latest supplied pre-cutoff Pass evidence includes 16 expired module records across seven current people: K0354, K0561, K1200, K1374, K1418, K1446 and K1483. K1200 accounts for five summary disagreements and nine expired detail records. This is a useful issuer-verification queue, not proof that the clean claim or detailed expiry is authoritative: renewal outside the supplied detail remains possible. MECS wording describes the documented consecutive sequence and never invents “Stage 0” or claims the person's actual awarded stage.

The output separately calculates nominal dates implied by the fictional scheme's renewal years as consistency checks. `Pass`, `Attended`, `Not achieved`, missing evidence, clean-summary disagreement and nominal-date disagreement remain distinct. The OSSC-SS/FF/FA and WAHS-1 record mapping is provisional because employer acceptance and climbing/rescue coverage are not specified. No GWO duration or external policy is imported as a binding Carrowmore rule.

The O&M posting requires hands-on mechanical **or** electrical experience. The separate HV Authorised Person posting's HVAP, switching-experience, AP-interview and familiarisation conditions are not imported as O&M interview gates. The HVAP scheme's insurer note leaves a scope ambiguity that requires employer clarification. Permit, isolation and practical checks in later actions are labelled recommended employer verification unless the supplied posting expressly requires them for a separate appointment.

Identity provenance distinguishes raw keeper codes, payroll references, names and absent identifiers. Integer-like payroll values are normalized across leading-zero, decimal and scientific notation without adding digits; for example, raw `1.1245E+04` corroborates K0147's clean `0011245`. Conflicting identifiers remain visible and clean/manual attribution remains explicit. Precise personnel dates are also checked against every retained work record: K0589/CL006691 and K1363/CL001473 predate the personnel export's joining dates, so both dates and their citations remain as unresolved discrepancies rather than deleting the work. Era-3 CSV row numbers include the header; era-2 citations use file plus record ID; era-1 citations use physical lines.

Quoted measurement anomalies are retained verbatim and flagged. Megger readings in `psi`/`bar`, pump delivery in volts and AVR voltage settings in ohms support only that an activity was recorded; their numerical measurements are not treated as reliable and no repair is invented.

For current profiles, selection happens first. Only after a positive selection outcome do later actions proceed through issuer/source verification, willingness and working-condition confirmation, medical clearance, module-specific OSSC work, dependent WAHS work, and employer permit/practical assessment. Each module action distinguishes a current Pass, expired Pass, Attended, Not achieved, conflict or missing evidence. An absent matched dated Pass now requires verification of any existing certificate first; training or assessment is conditional on coverage remaining unestablished. The posting's promise to fund renewals is reported only for renewals. The two leavers receive no training or mobilisation pathway.

Earlier repairs reduced canonical-pattern counts and added exact category citations without removing any original event. Under the corrected qualitative policy, K0566's four workflows still support an interview because CL010043 and CL006319 are specific attributed electrical and mechanical examples. K0310 also remains supported on cited historical work, while its profile states that supplied logs end in 2012 and no keyed appraisal exists; current practice is a question, not an invented recency rejection. K1345 retains both successful-work testimony and checking concerns, including a time-uncertain 2026 appraisal. The final policy follows cited experience and material contradictions; earlier unsupported count and appraisal-age gates were removed.

## Repository layout

```text
SOURCE_FINGERPRINTS.json       verified assessment and selected-source hashes
src/array_om_evaluator.py      deterministic file-based evaluator
qa/independent_qa.py           independent source/output and ten-case checks
output/recommendations.json    complete structured answer
output/recommendations.md      readable candidate-by-candidate answer
output/decision_brief.md       concise operator queue and reconciliation cases
output/qa_report.json          detailed QA evidence
output/run_metadata.json       interpreter, commands, repeatability and hashes
WRITTEN_EXPLANATION.md         concise final design reflection and effort statement
docs/DEVELOPMENT_HISTORY.md    preserved historical development notes
```

The source archive is not duplicated inside this repository. Supply its path with `--source-zip`; the required hash is recorded in `SOURCE_FINGERPRINTS.json` and enforced in code.

## Known limits

- This is a deliberately permitted 40-profile slice, not a ranking of all 340 current personnel in the source pack and not the separate 240-example ML mirror.
- Older name-only training is not guessed into identities. Clean aggregate certification summaries remain claims rather than independent issuer verification.
- Exact course availability, duration, price and fastest completion route are not in the sources and remain unknown.
- Work narratives support interview questions. They do not establish assessed competence, an appointment, current authorisation, or qualifying experience duration.
- Appraisals are manager testimony, sometimes internally conflicting and sometimes templated. They can define screening questions but do not establish competence or current authorisation.
- K1538's manager testimony remains an interview lead. Eleven years at Nevisbeg by 2011 implies a start around 2000, while the structured posting begins in 2009. The note also claims an authorisation under an unspecified earlier surname was lost in the 1997 changeover, while the personnel export records joining on 1998-08-05. Any pre-employment implication requires clarification; no surname, eligibility or authorisation is inferred.
- An alternate `--as-of` filters evidence but does not reconstruct the historical workforce. Current/leaver status remains the supplied roster snapshot.
- Unicode is preserved from the source. Where the supplied pack itself contains a replacement character, the JSON retains it and the readable report uses the supplied ASCII name where available.

See [WRITTEN_EXPLANATION.md](WRITTEN_EXPLANATION.md) for the required design reflection and effort statement.
