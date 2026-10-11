# Written explanation

## Scope and product decision

I built one file-based answer to the assessment's useful question: which current keepers in the permitted subset plausibly merit an Array O&M interview, and what must happen next? The source pack is entirely synthetic and was supplied for a Pearson job-application assessment. The implementation uses the allowed clean subset of 40 because four hours is better spent making person-level claims traceable than producing a broader but less defensible ranking. Thirty-eight profiles are current; K1203 and K1458 are visible only as leavers outside the redeployment cohort. This is not presented as the full population of 340 current staff or as the separate 240-example ML dataset.

The scenario cutoff is an explicit input and the submitted run uses 2026-10-11. The output separates interview potential, application eligibility and mobilisation readiness. Each experience claim carries the exact clean text and ID plus a resolvable raw citation. Each training claim preserves its exact outcome and supplied expiry. Future evidence is shown separately, contradictions stay visible, and missing evidence becomes a verification action rather than a claim that training never happened. Oileann/K1538's manager note and 11 kV entry are useful interview leads, but they are not turned into a current authorisation or two years of qualifying experience.

## What I did not build, and why

I did not build a UI, service, database, login system, deployment pipeline, broad data-cleaning platform, candidate rank from 1 to 38, or new ML model. None is needed to demonstrate the core judgement. SQL would make the submission less portable; the existing SQL mirror concerns the separate ML operation and intentionally does not contain the full assessment pack. A statistical model would conceal the small number of consequential rules behind another score. The deterministic output is easier for a reviewer to challenge line by line.

I also did not declare anyone mobilisation-ready. The sources do not establish current offshore medical fitness or current willingness to climb, enter enclosed spaces, transfer from a vessel, and work the stated rota. The supplied certification definitions also create a real interpretation issue: the posting asks for offshore safety including height, while OSSC contains no height module. I document WAHS-1 as the prototype's height mapping instead of pretending the posting specified the whole WAHS scheme. Prices, schedules and guaranteed fastest qualification routes remain unknown because the pack does not supply them.

## Where AI was wrong, and what I changed

The build benefited from treating AI output as a draft to be checked against sources:

1. The first source-manifest draft carried abbreviated/incorrectly transcribed hashes and guessed obsolete paths. Direct comparison with the preparation report and ZIP corrected them in a separate Git commit; history was not rewritten.
2. The first independent check treated two DAT keeper-key mismatches as importer failures. The audit shows that clean/manual attribution sometimes adds identity information to raw K8xxx/`UNKNOWN` records. I changed the answer and QA to preserve both claims: the activity resolves, but the raw key does not independently corroborate the clean person assignment.
3. A role-focused training filter initially hid K1200's future ANSM-C record. I changed future handling so every later LearnHub row is separated and visible even when its module is not a role gate.
4. The generic work-text rule did not select K1538's exact 11 kV sentence because its wording lacks the rule's usual action/plant vocabulary. I added the predeclared CL006360 hand-check beside the curated manager note and kept the explicit non-authorisation limitation.

These corrections are why the QA program is separate from the evaluator and why the ten representative cases were specified before the build.

## If this became a real product

I would throw away the regex shortlist score first. It is intentionally transparent and useful for this small synthetic slice, but it has no measured relationship to job performance and will miss unfamiliar phrasing. I would replace it only after agreeing a human review policy, gathering lawful and representative evidence, measuring subgroup impact, and defining appeal and correction routes.

I would keep the evidence contract: immutable source fingerprints, explicit scenario time, exact citations, outcome/expiry semantics, clean-versus-raw attribution, conflict preservation, and independent hand checks. I would also keep the separation between an interview lead, verified credential, assessed competence, employer appointment and mobilisation gate. Those boundaries matter more than the ranking mechanism.

## Effort

The focused implementation, generated run, independent QA, documentation and Git checkpoints were completed in one bounded session, comfortably inside the four-hour limit. The tracked active agent work was approximately 15 minutes at the documentation checkpoint. Earlier source audits, ML work and SQL reconciliation were preparation and are not represented as assessment build time; elapsed time for those separate activities is not invented or folded into this figure.
