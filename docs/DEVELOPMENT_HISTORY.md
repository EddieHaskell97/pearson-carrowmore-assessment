# Development history, preserved 11 October 2026

Historical record from local commit 011a45d. This preserves the previous long explanation; intermediate outcomes below are superseded where later sections say so. Use [the final explanation](../WRITTEN_EXPLANATION.md) and current recommendations for the final position. Agent execution intervals do not establish George's actual assessment effort.

---

# Written explanation

## Scope and product decision

I built one file-based answer to the assessment's useful question: which current keepers in the permitted subset plausibly merit an Array O&M interview, and what must happen next? The source pack is entirely synthetic and was supplied for a Pearson job-application assessment. The implementation uses the allowed clean subset of 40 because four hours is better spent making person-level claims traceable than producing a broader but less defensible ranking. Thirty-eight profiles are current; K1203 and K1458 are visible only as leavers outside the redeployment cohort. This is not presented as the full population of 340 current staff or as the separate 240-example ML dataset.

The scenario cutoff is an explicit input and the submitted run uses 2026-10-11. The output separates interview potential, application eligibility and mobilisation readiness. Each experience claim carries the exact clean text and ID plus a resolvable raw citation. Each training claim preserves its exact outcome and supplied expiry. Future evidence is shown separately, contradictions stay visible, and missing evidence becomes a verification action rather than a claim that training never happened. Oileann/K1538's manager note and 11 kV entry are useful interview leads, but they are not turned into a current authorisation or two years of qualifying experience. The note's eleven-year Nevisbeg claim is also shown to conflict with the 1998 joining date and the recorded Nevisbeg posting beginning in 2009.

## What I did not build, and why

I did not build a UI, service, database, login system, deployment pipeline, broad data-cleaning platform, candidate rank from 1 to 38, or new ML model. None is needed to demonstrate the core judgement. SQL would make the submission less portable; the existing SQL mirror concerns the separate ML operation and intentionally does not contain the full assessment pack. A statistical model would conceal the small number of consequential rules behind another score. The deterministic output is easier for a reviewer to challenge line by line.

I also did not declare anyone mobilisation-ready. The sources do not establish current offshore medical fitness or current willingness to climb, enter enclosed spaces, transfer from a vessel, and work the stated rota. The supplied certification definitions also create a real interpretation issue: the posting asks for offshore safety including height, while OSSC contains no height module. I document WAHS-1 as the prototype's height mapping instead of pretending the posting specified the whole WAHS scheme. Prices, schedules and guaranteed fastest qualification routes remain unknown because the pack does not supply them.

## Where AI was wrong, and what I changed

The build benefited from treating AI output as a draft to be checked against sources:

1. The first source-manifest draft carried abbreviated/incorrectly transcribed hashes and guessed obsolete paths. Direct comparison with the preparation report and ZIP corrected them in a separate Git commit; history was not rewritten.
2. The first independent check treated two DAT keeper-key mismatches as importer failures. The audit shows that clean/manual attribution sometimes adds identity information to raw K8xxx/`UNKNOWN` records. I changed the answer and QA to preserve both claims: the activity resolves, but the raw key does not independently corroborate the clean person assignment.
3. A role-focused training filter initially hid K1200's future ANSM-C record. I changed future handling so every later LearnHub row is separated and visible even when its module is not a role gate.
4. The generic work-text rule did not select K1538's exact 11 kV sentence because its wording lacks the rule's usual action/plant vocabulary. I added the predeclared CL006360 hand-check beside the curated manager note and kept the explicit non-authorisation limitation.
5. The final profile sanity pass showed that the action vocabulary missed irregular and trade-specific wording such as “rebuilt” and “dressed,” which hid K1200's motor and clockwork maintenance. I added those explicit verbs and regenerated the whole answer rather than manually changing that person's result.

The bounded correction pass then made the evidence contract stricter:

- CL005994's motor-brush and commutator work is consistently categorized as both electrical and mechanical. Under the documented non-ranking rule, K1200 changes from `consider_interview` to `recommend_interview`; no other recommendation changes.
- Supplied module expiries remain untouched, while nominal scheme-rule dates are shown separately. Four cutoff-changing conflicts are visible: K0274/LH500295, K1200/LH502297, K1200/LH502305 and K1345/LH502579. Each is unresolved pending issuer verification.
- Suspect units in quoted work records are preserved and warned about. The activity can support an interview question, but the number is not treated as reliable evidence.
- Era-3 identity handling now reads its actual versioned headers. It distinguishes names from payroll IDs and normalizes only integer-like numeric/scientific payroll representations. Conflicts and absent identifiers remain explicit.
- Leavers no longer receive a training or mobilisation route. Current-person actions now respect verification, willingness, medical, OSSC and WAHS dependencies, and quote the employer's renewal funding narrowly.

These corrections are why the QA program is separate from the evaluator and why the ten representative cases were specified before the build.

## Decision-quality correction

The next review found a material omission: the evaluator had not read `raw/appraisals/appraisals.jsonl`. I added that member to the enforced source manifest rather than treating the already curated Oileann note as representative of all appraisals. The file has SHA-256 `c19ba6216619c0c4d103b5dd7d99edb49f9722fba94a6eb9de824adfba1488d1` and contains 4,422 JSONL rows. Of those, 2,694 carry a keeper code, 1,728 do not, and 305 are exactly keyed to 37 of the 38 current profiles. K0310 has no keyed appraisal. The join is deliberately exact: I did not attach null-key or name-only records, even where a name looked plausible.

Every clean log row and every exactly keyed current-person appraisal is now reviewed. Repeated log templates and superficial numeric variants are collapsed before judging evidence diversity; the readable output shows the strongest records while the structured output records the full-history counts. Appraisal processing keeps the source year as year precision, uses 2026 records only as context because their timing relative to 2026-10-11 is unknown, and excludes future years from current conclusions. It retains exact filter-selected excerpts plus a hash of the complete source text. Unmatched rows are described only as “not selected by the appraisal filter,” not characterized as irrelevant.

The decision policy is a set of gates rather than a score. `supported_technical_interview` requires at least five distinct relevant log patterns and no explicit role-related appraisal concern in the ten years before the cutoff. `targeted_screening_first` means relevant evidence exists but is sparse/repetitive or a recent explicit concern requires a focused evidence screen first. `insufficient_evidence` is reserved for fewer than three distinct patterns without strong keyed manager support. Leavers remain outside the current cohort. No category creates a rank, competence finding, eligibility decision or mobilisation decision.

That policy changed the old blanket 38-interview output to 22 supported technical interviews and 16 targeted screens. No current profile fell into insufficient evidence. The 16 targeted screens are K0147, K0184, K0303, K0354, K0394, K0478, K0561, K0586, K0589, K0897, K1200, K1231, K1345, K1446, K1483 and K1538. This count is an outcome, not a target.

The named hand checks explain the judgement:

- K1200's CL005994, CL007505, CL009097 and CL009921 are retained as hands-on work evidence, while AP003496 says the course record exceeds the manager's observed plant experience and records avoidance of two requests to assist. The contradiction produces targeted screening; neither source is erased.
- K0561/AP001433, K1231/AP003571 and K1446/AP004147/AP004150 retain specific supervision, checked-work and height/staging concerns alongside their positive evidence.
- K0586 is routed cautiously because only three distinct technical log patterns survive template collapse and no strong directly technical keyed appraisal supplies the missing breadth.
- K0371/AP000798 and K0847/AP002309 retain stronger manager testimony alongside their logs. It is a useful interview lead, not proof of competence or authorisation.
- Oileann/K1538 retains the curated chronology warning, exact keyed positive appraisal AP004418 and later gap AP004422. The result remains a targeted screen, not a current HV authorisation.

Selection and mobilisation are now explicitly two stages. The immediate action is either a structured technical interview, a targeted evidence screen or a request for verifiable evidence. Course, medical and mobilisation instructions appear only under a conditional later stage. Each essential module action now says whether the record is a current Pass, expired Pass, Attended, Not achieved, conflicted or absent; employer funding is stated only for renewals.

## Verified defect repair

A bounded repair corrected four implementation defects without changing the scope, 2026-10-11 scenario date or decision policy:

- The Markdown experience loop had accidentally been nested under the presence of a same-year uncertain appraisal. It now renders every retained work record in every profile, including exact date, text, source reference, attribution and any measurement warning. Independent QA locates each retained record inside its own profile section.
- Canonical pattern counting now treats a numeric measurement and its supplied unit as one replaceable slot. Thus otherwise identical Megger templates containing `3.6 bar`, `48 psi` or `11.2 V` share one pattern. K1200's four named records remain readable evidence, but their IDs do not create separate pattern identities and the display-only mercury-bath record does not enter the normal qualifying-pattern count.
- Where no matched dated Pass exists, the action now requires issuer verification of any existing certificate first. Training and assessment are prescribed only if current required coverage remains unestablished. Current, expired, Attended, Not achieved and conflicting records keep their distinct actions.
- The appraisal selector now retains K0147/AP000090's positive rope-work testimony and K0354/AP000752/AP000753's work-reporting concerns. Rope completion is explicitly decision-neutral context, and work-reporting is not one of the primary technical topics that changes the concern gate. Positive and contrary excerpts remain together without automatic promotion or rejection.

Corrected canonicalization reduced pattern counts for 15 profiles: K0303 10→8, K0371 10→7, K0482 12→9, K0561 7→6, K0592 12→10, K0650 12→10, K0847 15→10, K0897 8→7, K1200 7→3, K1231 13→12, K1302 7→6, K1458 14→11, K1468 15→13, K1511 10→8 and K1538 17→12. No profile crossed an unchanged decision gate, so there were no disposition changes and the observed result remains 22 supported technical interviews, 16 targeted screens, zero insufficient and two outside the cohort.

## If this became a real product

I would replace the regex evidence gates first. They are intentionally transparent and useful for this small synthetic slice, but they have no measured relationship to job performance, can miss unfamiliar phrasing and cannot resolve contradictory manager testimony. I would replace them only after agreeing a human review policy, gathering lawful and representative evidence, measuring subgroup impact, and defining appeal and correction routes.

I would keep the evidence contract: immutable source fingerprints, explicit scenario time, exact citations, outcome/expiry semantics, clean-versus-raw attribution, conflict preservation, and independent hand checks. I would also keep the separation between an interview lead, verified credential, assessed competence, employer appointment and mobilisation gate. Those boundaries matter more than the ranking mechanism.

## Effort

The initial build's completion timer recorded 1,118 seconds (18 minutes 38 seconds) of active agent execution; the earlier “approximately 15 minutes” wording was a provisional documentation-checkpoint figure and is superseded. The first bounded correction was not instrumented and therefore remains recorded as **not measured**. The decision-quality correction was separately measured from 2026-10-11 14:01:00.968 -04:00 through final output/QA/repeatability verification at 14:15:44.230 -04:00: **883 seconds (14 minutes 43 seconds)**. This verified defect repair was separately measured from 14:24:46.537 -04:00 through final regenerated-output, QA and repeatability verification at 14:30:57.726 -04:00: **371 seconds (6 minutes 11 seconds)**. Metadata and local Git bookkeeping followed each interval and are excluded. The exact timestamps and scopes are preserved in `output/run_metadata.json`; these intervals are not added to the earlier build. Earlier source audits, ML work and SQL reconciliation were preparation and remain separately accounted; their elapsed time is not invented or folded into assessment-build time.
