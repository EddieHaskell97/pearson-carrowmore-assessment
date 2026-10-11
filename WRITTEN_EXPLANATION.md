# Written explanation

## Scope and deliberate cuts

I focused on which current keepers in the permitted clean subset plausibly merit an Array O&M interview, and what each needs first. The pack is entirely synthetic. Using its 40 profiles let me concentrate on traceable person-level decisions: 38 are current, while K1203 and K1458 are leavers outside the cohort. This is not a shortlist from all 340 keepers.

The final result is 21 supported technical interviews and 17 targeted screens. These counts are outcomes, not quotas. The screens address sparse or repetitive evidence and specific appraisal concerns. Five distinct relevant work patterns, with no selected recent role-related concern, support an interview under this prototype policy. That threshold is my transparent design choice, not an employer requirement or a validated predictor of job performance.

I did not build a UI, service, database, deployment pipeline, ML model, full-population identity resolver or candidate ranking. The employer posting gives a more direct starting point than a broad skills-taxonomy mapping. Markdown and JSON make this bounded answer portable and inspectable. I used a small independent QA harness because a wrong citation or cutoff would undermine the central claim of traceability; passing checks does not validate recruitment judgment.

The explicit scenario date is 2026-10-11, not an inferred Pearson date. Current medical fitness, willingness and authorisation remain unestablished. The answer gives a selection step now and conditional verification, medical and training steps if the person progresses. An absent training record triggers certificate verification before prescribing a course. The employer's funding promise applies to renewals.

## Where I took the work back from AI

The initial answer recommended interviewing all 38 current keepers. I challenged that blanket conclusion. The evaluator had omitted the main appraisal file, so I required it to reconcile work logs with exactly keyed appraisal evidence. K1200 now receives targeted screening: CL005994 records motor-brush and commutator work, while AP003496 questions observed plant experience and records avoidance of assistance requests. Both claims remain visible; neither automatically wins. Null-key appraisals remain unattached, not evidence that a person had no concerns.

Further source-to-output review found work records missing from Markdown and superficial measurement and permit-document wording inflating evidence diversity. The repairs render every retained record, collapse equivalent numeric/unit and `permit` / `PTW` / `permit bk.` workflow variants only in the counting key, and cite an exact displayed work record for every claimed category. Original events, dates, quotes and citations remain unchanged. K1200's four named work records remain visible, but three canonical patterns count toward the decision. The independently verified permit collapse reduced K0566 from six patterns to four, moving that profile from a supported interview to targeted screening under the unchanged gate; no count was forced.

I also preserved conflicting certificate expiries and suspect measurement units rather than silently correcting them. K1538's 2011 manager note claims eleven years at Nevisbeg, implying about 2000, while the structured posting starts in 2009. This is conflicting testimony to investigate, not proof of current HV authorisation. The 1998 joining date is not itself the contradiction. K0310 remains a supported interview lead, but the output explicitly says that supplied logs end in 2012 and there is no keyed appraisal; I did not invent a recency threshold or use that limitation as an automatic rejection.

## What I would replace and keep

I would replace the regex selectors, numerical gates and person-specific display exceptions first. They can miss unfamiliar wording and have no demonstrated relationship to job performance. A real product would need an agreed human assessment policy, better attribution and representative evaluation before these gates could support operational decisions.

I would keep immutable source fingerprints, exact category and work citations, explicit scenario time, separate training outcomes and expiry claims, visible contradictions, and independent source checks. Most importantly, I would preserve the distinction between evidence of work, an interview lead, verified credentials, assessed competence and employer authorisation.

## Effort

I spent approximately two to four hours on the assessment-specific work and review, excluding the separate personal ML/SQL lab. Agent execution intervals are recorded separately in the run metadata; they do not establish my total time. The detailed development record is retained in Git and [docs/DEVELOPMENT_HISTORY.md](docs/DEVELOPMENT_HISTORY.md).
