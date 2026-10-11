#!/usr/bin/env python3
"""Bounded, evidence-first evaluator for the synthetic Carrowmore assessment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


ROOT = "carrowmore-data-pack/"
KEEPERS = ROOT + "clean/keepers.json"
LOGS = ROOT + "clean/logbook_entries.json"
LEARNHUB = ROOT + "raw/training/vendor-c-learnhub-2017-2026.json"
SCHEMES = ROOT + "employers/certification_schemes.json"
POSTING = ROOT + "employers/carrowmore-array-om-technician.md"
CURRENT = ROOT + "raw/personnel/cla_personnel_export.csv"
LEAVERS = ROOT + "raw/personnel/cla_personnel_leavers.csv"
OILEANN_NOTE = ROOT + "raw/appraisals/station_manager_notes/2011-nevisbeg-keeper-note.txt"

EXPECTED_ARCHIVE_HASH = "59f12ea4dfb43d311429fdd34c207517c2ffefbf917e4cdfe9737ca5776270f5"
EXPECTED_MEMBER_HASHES = {
    KEEPERS: "5aa6e0a811b5d49da43d524d86023163aea90ff67db32143be1821cba554d58b",
    LOGS: "b7b247d406d4faa538c1880991b2f85d6c1b2b9c4300a02b7834850cc9324a95",
    LEARNHUB: "a8d0f1a3dab7ad6f430e7352c72e434c01d8b38ca1cec3d4de26a2fdd4403c2b",
    SCHEMES: "51ea3687808118b5aefe1707de26f2c87661ba20df6c542d98ac3b4f237de4ef",
    POSTING: "64b86a9bafe79f01757495cbf0eebde11e0cb5f680d21928cd0cf0ecbdfa6d0c",
    CURRENT: "14ba3653d9ab29b86b273cb7016dba574d840729de85d5b0eac367ed3170b4c7",
    LEAVERS: "920f7a76d3710ac08a56d7bf9ac0de83cf65f5525e8c7a1dfc905b517d2d9a0a",
    OILEANN_NOTE: "767fa1decaafb6e56556ca7416b069e07cebf85a2cbd5d3c2d661df85d08adc4",
}

ACTION_RE = re.compile(
    r"\b(repair(?:ed|ing)?|replac(?:e|ed|ing)|renew(?:ed|ing)?|servic(?:e|ed|ing)|"
    r"maintain(?:ed|ing)?|test(?:ed|ing)?|check(?:ed|ing)?|inspect(?:ed|ing)?|"
    r"strip(?:ped|ping)?|adjust(?:ed|ing)?|trace(?:d|ing)?|diagnos(?:e|ed|ing)|"
    r"isolat(?:e|ed|ing)|greas(?:e|ed|ing)|fit(?:ted|ting)?|chang(?:e|ed|ing)|"
    r"overhaul(?:ed|ing)?|calibrat(?:e|ed|ing)|tighten(?:ed|ing)?|rewir(?:e|ed|ing)|"
    r"rebuild(?:s|ing)?|rebuilt|dismantl(?:e|ed|ing)|dress(?:ed|ing)|align(?:ed|ing)|"
    r"investigat(?:e|ed|ing)|fault[- ]?find(?:ing)?|clean(?:ed|ing)?)\b",
    re.I,
)

CATEGORY_PATTERNS = {
    "electrical": re.compile(
        r"\b(electrical|voltage|volt(?:age)?s?|earth fault|continuity|breaker|switchgear|"
        r"relay|contactor|cable|wiring|fuse|battery|charger|alternator|transformer|"
        r"insulation|megger|clamp meter|rectifier|control gear|generator controls?)\b",
        re.I,
    ),
    "mechanical": re.compile(
        r"\b(engine|generator|pump|motor|compressor|hydraulic|bearing|shaft|fuel|oil|"
        r"filter|belt|gearbox|gear|drive|ratchet|commutator|clockwork|valve|cooling|"
        r"lubrication|lubricated|fan)\b",
        re.I,
    ),
    "fault_finding": re.compile(
        r"\b(fault|traced?|diagnos\w*|continuity|meter|megger|insulation|trip(?:ped|ping)?|"
        r"intermittent|proved dead|found the cause)\b",
        re.I,
    ),
    "permit_or_isolation": re.compile(
        r"\b(permit|isolation|isolat\w*|lockout|proved dead|switching|earthed)\b", re.I
    ),
    "work_at_height": re.compile(
        r"\b(fall arrest|harness|vertical ladder|tower climb|aloft|nacelle|roof work)\b", re.I
    ),
    "mentoring": re.compile(
        r"\b(trained|coached|mentored|showed the new|apprentice|younger colleague)\b", re.I
    ),
}

RELEVANT_TRAINING_PREFIXES = ("OSSC-", "WAHS-", "MECS-", "MPMC-", "HVAP-", "LOSC-")
ESSENTIAL_MODULES = {
    "sea_survival": "OSSC-SS",
    "fire": "OSSC-FF",
    "first_aid": "OSSC-FA",
    "working_at_height": "WAHS-1",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def read_json(zf: zipfile.ZipFile, name: str):
    return json.loads(zf.read(name).decode("utf-8"))


def verify_inputs(zip_path: Path, zf: zipfile.ZipFile) -> dict:
    archive_hash = sha256(zip_path.read_bytes())
    if archive_hash != EXPECTED_ARCHIVE_HASH:
        raise ValueError(f"source archive hash mismatch: {archive_hash}")
    actual = {}
    for member, expected in EXPECTED_MEMBER_HASHES.items():
        value = sha256(zf.read(member))
        actual[member.removeprefix(ROOT)] = value
        if value != expected:
            raise ValueError(f"member hash mismatch for {member}: {value}")
    if len(zf.namelist()) != 1447:
        raise ValueError(f"expected 1447 archive members, found {len(zf.namelist())}")
    return {"archive_sha256": archive_hash, "archive_members": 1447, "member_sha256": actual}


def parse_personnel(zf: zipfile.ZipFile, member: str) -> list[dict]:
    text = zf.read(member).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def raw_corroboration(zf: zipfile.ZipFile, entry: dict) -> dict:
    """Resolve a clean citation at the source format's declared granularity."""
    source, locator = entry["source_record"].split("#", 1)
    member = ROOT + source
    raw = zf.read(member)
    result = {"reference": entry["source_record"], "format": f"era{entry['source_era']}", "resolved": False}
    if entry["source_era"] == 1:
        line_no = int(locator.removeprefix("L"))
        lines = raw.decode("utf-8", errors="replace").splitlines()
        if not (1 <= line_no <= len(lines)):
            return result
        result.update(resolved=True, resolution="physical_line", raw_excerpt=lines[line_no - 1].strip())
        return result
    if entry["source_era"] == 2:
        rec_id = locator
        for line in raw.decode("cp1252", errors="replace").splitlines():
            if line.startswith(rec_id + "|"):
                fields = line.split("|")
                result.update(
                    resolved=True,
                    resolution="file_and_record_id",
                    raw_keeper=fields[3],
                    raw_keeper_name=fields[4],
                    raw_activity=fields[6],
                    attribution_match=fields[3] == entry["keeper_code"],
                )
                return result
        return result
    row_no = int(locator)
    lines = raw.decode("utf-8-sig", errors="replace").splitlines()
    if not (2 <= row_no <= len(lines)):
        return result
    row = next(csv.reader([lines[row_no - 1]]))
    result.update(
        resolved=True,
        resolution="physical_csv_row_including_header",
        raw_keeper_name=row[2],
        raw_activity=row[3].lstrip("'"),
        attribution_match=None,
    )
    return result


def entry_categories(text: str) -> list[str]:
    return [name for name, pattern in CATEGORY_PATTERNS.items() if pattern.search(text)]


def select_work_evidence(zf: zipfile.ZipFile, entries: list[dict], as_of: date) -> list[dict]:
    candidates = []
    for entry in entries:
        if parse_date(entry["date"]) > as_of or not ACTION_RE.search(entry["text"]):
            continue
        categories = entry_categories(entry["text"])
        if not ({"electrical", "mechanical"} & set(categories)):
            continue
        score = 2 * len({"electrical", "mechanical", "fault_finding", "permit_or_isolation"} & set(categories))
        score += len(set(categories))
        candidates.append((score, entry["date"], entry, categories))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]["entry_id"]), reverse=True)
    chosen, normalized_seen = [], set()
    for score, _, entry, categories in candidates:
        # Collapse superficial asset-number and measurement variants so repeated
        # synthetic templates do not masquerade as diverse experience.
        normalized = re.sub(r"\d+(?:\.\d+)?", "#", entry["text"].lower())
        normalized = re.sub(r"\bno\s*\.?\s*#", "no #", normalized)
        normalized = re.sub(r"\W+", " ", normalized).strip()
        if normalized in normalized_seen:
            continue
        corroboration = raw_corroboration(zf, entry)
        if not corroboration["resolved"]:
            raise ValueError(f"unresolved source reference {entry['source_record']}")
        chosen.append(
            {
                "entry_id": entry["entry_id"],
                "date": entry["date"],
                "text": entry["text"],
                "station": entry["station"],
                "categories": categories,
                "clean_source": "clean/logbook_entries.json",
                "source_reference": entry["source_record"],
                "attribution": "clean_manual_attribution",
                "raw_corroboration": corroboration,
                "selection_score": score,
            }
        )
        normalized_seen.add(normalized)
        if len(chosen) == 5:
            break
    return chosen


def training_status(record: dict, as_of: date) -> str:
    completed = parse_date(record.get("completed_on"))
    expires = parse_date(record.get("expires_on"))
    if completed and completed > as_of:
        return "future_at_cutoff"
    outcome = record.get("outcome")
    if outcome == "Not achieved":
        return "not_achieved"
    if outcome == "Attended":
        return "attended_not_passed"
    if outcome != "Pass":
        return "outcome_not_a_pass"
    if expires and expires < as_of:
        return "pass_expired"
    return "pass_current_at_cutoff" if expires else "pass_no_expiry_recorded"


def build_training(keeper: dict, learnhub_rows: list[dict], as_of: date) -> tuple[list[dict], list[dict]]:
    claims, future = [], []
    for row in sorted(learnhub_rows, key=lambda x: (x.get("completed_on") or "", x["id"])):
        module = row.get("scheme_module") or ""
        claim = {
            "record_id": row["id"],
            "module": module,
            "title": row["title"],
            "outcome": row["outcome"],
            "completed_on": row.get("completed_on"),
            "expires_on": row.get("expires_on"),
            "status_at_cutoff": training_status(row, as_of),
            "source_reference": f"raw/training/vendor-c-learnhub-2017-2026.json#{row['id']}",
        }
        if claim["status_at_cutoff"] == "future_at_cutoff":
            future.append(claim)
        elif module.startswith(RELEVANT_TRAINING_PREFIXES):
            claims.append(claim)
    return claims, future


def current_module(claims: list[dict], module: str) -> bool:
    return any(c["module"] == module and c["status_at_cutoff"] == "pass_current_at_cutoff" for c in claims)


def clean_completed_modules(keeper: dict, scheme: str) -> set[str]:
    return {
        row["module"]
        for row in keeper.get("training_records", [])
        if row.get("scheme") == scheme and row.get("outcome") == "completed"
    }


def credential_conflicts(keeper: dict, claims: list[dict], as_of: date) -> list[dict]:
    conflicts = []
    ss_current = current_module(claims, "OSSC-SS")
    clean_certs = {c["scheme"]: c for c in keeper.get("certifications", [])}
    for scheme in ("WAHS", "SMOC"):
        cert = clean_certs.get(scheme)
        if cert and cert.get("valid_2026") and not ss_current:
            conflicts.append(
                {
                    "code": "prerequisite_not_established",
                    "scheme": scheme,
                    "claim": "Clean summary marks the award valid in 2026.",
                    "finding": "A current OSSC-SS prerequisite is not established by the dated LearnHub rows supplied.",
                    "source_references": [
                        f"clean/keepers.json#{keeper['keeper_code']}/certifications/{scheme}",
                        "employers/certification_schemes.json#" + scheme,
                    ],
                }
            )
    losc = {c["module"]: c for c in claims if c["module"].startswith("LOSC-") and c["outcome"] == "Pass"}
    if "LOSC-P" in losc:
        p_date = losc["LOSC-P"].get("completed_on") or "9999-12-31"
        if any(m not in losc or (losc[m].get("completed_on") or "9999-12-31") > p_date for m in ("LOSC-S", "LOSC-A")):
            conflicts.append(
                {
                    "code": "prerequisite_chronology_not_established",
                    "scheme": "LOSC",
                    "claim": "A LOSC-P pass is present.",
                    "finding": "The supplied rows do not establish both prerequisite passes on or before LOSC-P; an earlier unrepresented pass remains possible.",
                    "source_references": [losc["LOSC-P"]["source_reference"], "employers/certification_schemes.json#LOSC"],
                }
            )
    completed_mecs = clean_completed_modules(keeper, "MECS")
    highest = 0
    for stage in range(1, 6):
        if f"MECS-{stage}" in completed_mecs:
            highest = stage
        else:
            break
    later = sorted(m for m in completed_mecs if int(m.split("-")[1]) > highest)
    if later:
        conflicts.append(
            {
                "code": "consecutive_stage_not_established",
                "scheme": "MECS",
                "claim": f"Completed modules include {', '.join(sorted(completed_mecs))}.",
                "finding": f"The defined cumulative stage is only Stage {highest}; later modules do not bridge missing earlier stages.",
                "source_references": [f"clean/keepers.json#{keeper['keeper_code']}/training_records", "employers/certification_schemes.json#MECS"],
            }
        )
    return conflicts


def safety_coverage(claims: list[dict]) -> dict:
    return {
        need: {"module": module, "dated_pass_current": current_module(claims, module)}
        for need, module in ESSENTIAL_MODULES.items()
    }


def clean_summaries(keeper: dict) -> list[dict]:
    relevant = {"OSSC", "WAHS", "MECS", "MPMC", "HVAP", "SMOC", "LOSC"}
    return [
        {
            "scheme": c["scheme"],
            "modules_held": c.get("modules_held", []),
            "modules_missing": c.get("modules_missing", []),
            "complete": c.get("complete"),
            "awarded_year": c.get("awarded_year"),
            "expires_year": c.get("expires_year"),
            "valid_2026": c.get("valid_2026"),
            "status": "clean_summary_claim_not_independent_verification",
            "source_reference": f"clean/keepers.json#{keeper['keeper_code']}/certifications/{c['scheme']}",
        }
        for c in keeper.get("certifications", [])
        if c.get("scheme") in relevant
    ]


def evaluate_keeper(zf, keeper, entries, learnhub_rows, as_of):
    evidence = select_work_evidence(zf, entries, as_of)
    claims, future = build_training(keeper, learnhub_rows, as_of)
    conflicts = credential_conflicts(keeper, claims, as_of)
    coverage = safety_coverage(claims)
    categories = sorted({c for item in evidence for c in item["categories"]})
    is_current = keeper["status"] == "current"

    if not is_current:
        recommendation = "outside_current_redeployment_cohort"
        reason = "The clean profile and leavers export mark this person as having left; no current redeployment recommendation is made."
        eligibility = "not_assessed_outside_current_cohort"
    elif len(evidence) >= 3 and ({"electrical", "mechanical"} <= set(categories) or "fault_finding" in categories):
        recommendation = "recommend_interview"
        reason = "The bounded records contain multiple directly cited maintenance examples, including diagnostic or cross-discipline evidence. Interview is warranted; competence is not inferred."
        eligibility = "plausible_but_essential_evidence_incomplete"
    elif evidence:
        recommendation = "consider_interview"
        reason = "At least one directly cited plant-maintenance example is present, but the bounded evidence is too narrow for a stronger recommendation."
        eligibility = "plausible_but_essential_evidence_incomplete"
    else:
        recommendation = "insufficient_evidence_in_subset"
        reason = "No directly actionable electrical or mechanical maintenance example met the transparent evidence rule in this bounded subset."
        eligibility = "not_established_from_bounded_evidence"

    gaps = []
    for need, item in coverage.items():
        if not item["dated_pass_current"]:
            gaps.append(f"Obtain or verify a current dated Pass for {item['module']} ({need.replace('_', ' ')}).")
    gaps.extend([
        "Obtain a current offshore medical fitness declaration.",
        "Confirm directly that the person accepts 80 m tower work, enclosed spaces, vessel transfer and the 14-on/14-off pattern.",
        "Assess hands-on skill under the employer's permit, isolation and task standards before mobilisation.",
    ])
    limitations = [
        {"code": "competence_not_inferred", "text": "Examples support interview potential only; tags, grades, hours and occurrence counts were not treated as proof of competence."},
        {"code": "medical_not_supplied", "text": "No current offshore medical evidence is present in the bounded sources."},
    ]
    supplementary = []
    if keeper["keeper_code"] == "K1538":
        switching_entry = next(e for e in entries if e["entry_id"] == "CL006360")
        switching_raw = raw_corroboration(zf, switching_entry)
        if not switching_raw["resolved"]:
            raise ValueError("unresolved Oileann hand-check citation CL006360")
        supplementary.append(
            {
                "claim": "A 2011 manager note records generator-control fault-finding and years of station high-voltage switching; clean entry CL006360 records work on an 11 kV board.",
                "source_reference": "raw/appraisals/station_manager_notes/2011-nevisbeg-keeper-note.txt#L3,L7,L9,L11",
                "supporting_entry": {
                    "entry_id": switching_entry["entry_id"],
                    "date": switching_entry["date"],
                    "text": switching_entry["text"],
                    "source_reference": switching_entry["source_record"],
                    "attribution": "clean_manual_attribution",
                    "raw_corroboration": switching_raw,
                },
                "attribution_basis": "The note names NI GHARBHAIL O/Oileann; the personnel export has one exact NI GHARBHAIL O match and the clean profile places K1538 at Nevisbeg in 2011.",
                "use": "interview_lead_only",
            }
        )
        limitations.append(
            {"code": "authorization_not_established", "text": "The manager's narrative is not a currently recognised authorisation and does not establish two years of qualifying 11 kV experience."}
        )

    return {
        "keeper_code": keeper["keeper_code"],
        "name": keeper["name"],
        "name_ascii": keeper.get("name_ascii"),
        "cohort_status": "current_redeployment_cohort" if is_current else "leaver_outside_current_cohort",
        "as_of": as_of.isoformat(),
        "interview_recommendation": recommendation,
        "recommendation_reason": reason,
        "application_eligibility": eligibility,
        "mobilisation_readiness": "not_established",
        "relevant_experience": evidence,
        "supplementary_evidence": supplementary,
        "experience_categories": categories,
        "credential_claims": claims,
        "clean_certification_summaries": clean_summaries(keeper),
        "credential_conflicts": conflicts,
        "future_evidence_not_used": future,
        "essential_coverage_from_dated_passes": coverage,
        "remaining_requirements": gaps,
        "next_actions": [
            "If shortlisted, validate each cited example in a structured technical interview.",
            "Resolve listed credential conflicts against original certificates or issuer records.",
            "Complete employer practical assessment, medical and role-specific safety gap training before mobilisation.",
        ],
        "limitations": limitations,
    }


def markdown_report(payload: dict) -> str:
    summary = payload["summary"]
    lines = [
        "# Array O&M candidate recommendations",
        "",
        "> Synthetic Carrowmore data supplied for a Pearson job-application assessment. These are bounded development recommendations, not employment decisions.",
        "",
        f"Scenario date: **{payload['as_of']}**  ",
        f"Subset: **{summary['profiles']} profiles — {summary['current']} current keepers and {summary['leavers']} leavers outside the redeployment cohort**  ",
        f"Results: **{summary['recommend_interview']} recommend interview, {summary['consider_interview']} consider interview, {summary['insufficient_evidence']} insufficient bounded evidence**",
        "",
        "Interview potential is deliberately separate from application eligibility and mobilisation readiness. No person is marked mobilisation-ready because medical fitness and direct acceptance of height/boat/enclosed-space conditions are not supplied.",
        "",
    ]
    ordering = {"recommend_interview": 0, "consider_interview": 1, "insufficient_evidence_in_subset": 2, "outside_current_redeployment_cohort": 3}
    for row in sorted(payload["candidates"], key=lambda r: (ordering[r["interview_recommendation"]], r["keeper_code"])):
        lines.extend([
            f"## {row['keeper_code']} — {row['name_ascii'] or row['name']}",
            "",
            f"- Interview: `{row['interview_recommendation']}` — {row['recommendation_reason']}",
            f"- Application eligibility: `{row['application_eligibility']}`",
            f"- Mobilisation readiness: `{row['mobilisation_readiness']}`",
            f"- Relevant evidence categories: {', '.join(row['experience_categories']) or 'none found'}",
            "",
        ])
        if row["relevant_experience"]:
            lines.append("Evidence:")
            lines.append("")
            for e in row["relevant_experience"]:
                raw = e["raw_corroboration"]
                if raw.get("attribution_match") is False:
                    attribution = f"clean/manual attribution; raw activity resolves but carries {raw.get('raw_keeper')}/{raw.get('raw_keeper_name')}, so the raw key does not independently corroborate the person assignment"
                elif raw.get("attribution_match") is True:
                    attribution = "clean/manual attribution corroborated by the raw keeper key"
                else:
                    attribution = "clean/manual attribution; raw reference resolves but its format has no keeper code"
                lines.append(f"- {e['date']} — “{e['text']}” ({e['entry_id']}; `{e['source_reference']}`; {attribution}).")
            lines.append("")
        for e in row["supplementary_evidence"]:
            lines.append(f"- Supplementary note: {e['claim']} (`{e['source_reference']}`). {e['attribution_basis']} This is an interview lead, not an authorisation.")
            if e.get("supporting_entry"):
                s = e["supporting_entry"]
                lines.append(f"- Hand-check entry: {s['date']} — “{s['text']}” ({s['entry_id']}; `{s['source_reference']}`).")
            lines.append("")
        current_passes = [c for c in row["credential_claims"] if c["status_at_cutoff"] == "pass_current_at_cutoff"]
        lines.append("Credential position:")
        lines.append("")
        if current_passes:
            for c in current_passes:
                lines.append(f"- Dated Pass: {c['module']}, completed {c['completed_on']}, supplied expiry {c['expires_on']} (`{c['source_reference']}`).")
        else:
            lines.append("- No currently dated relevant LearnHub Pass was established at the cutoff.")
        for c in row["credential_claims"]:
            if c["status_at_cutoff"] in {"not_achieved", "attended_not_passed", "pass_expired"}:
                lines.append(f"- {c['module']}: {c['outcome']}; `{c['status_at_cutoff']}` (`{c['source_reference']}`).")
        for c in row["credential_conflicts"]:
            lines.append(f"- Conflict `{c['code']}`: {c['finding']}")
        if row["future_evidence_not_used"]:
            ids = ", ".join(x["record_id"] for x in row["future_evidence_not_used"])
            lines.append(f"- Future at cutoff and not used: {ids}.")
        lines.extend(["", "First actions:", ""])
        for action in row["remaining_requirements"][:6]:
            lines.append(f"- {action}")
        lines.append("")
    return "\n".join(lines) + "\n"


def build(zip_path: Path, as_of: date) -> dict:
    with zipfile.ZipFile(zip_path) as zf:
        fingerprints = verify_inputs(zip_path, zf)
        keepers = read_json(zf, KEEPERS)
        logs = read_json(zf, LOGS)
        learnhub = read_json(zf, LEARNHUB)["records"]
        schemes = read_json(zf, SCHEMES)["schemes"]
        current_people = parse_personnel(zf, CURRENT)
        leavers = parse_personnel(zf, LEAVERS)
        if len(keepers) != 40 or Counter(k["status"] for k in keepers) != {"current": 38, "left": 2}:
            raise ValueError("clean subset is not the expected 38 current / 2 left")
        current_ids = {r["keeper_code"] for r in current_people}
        leaver_ids = {r["keeper_code"] for r in leavers}
        for k in keepers:
            expected = current_ids if k["status"] == "current" else leaver_ids
            if k["keeper_code"] not in expected:
                raise ValueError(f"personnel cohort conflict for {k['keeper_code']}")
        by_keeper_logs = defaultdict(list)
        by_keeper_training = defaultdict(list)
        for row in logs:
            by_keeper_logs[row["keeper_code"]].append(row)
        for row in learnhub:
            by_keeper_training[row["keeper_code"]].append(row)
        candidates = [
            evaluate_keeper(zf, k, by_keeper_logs[k["keeper_code"]], by_keeper_training[k["keeper_code"]], as_of)
            for k in sorted(keepers, key=lambda x: x["keeper_code"])
        ]
    counts = Counter(c["interview_recommendation"] for c in candidates)
    return {
        "schema_version": 1,
        "dataset": "synthetic Carrowmore Pearson assessment pack",
        "as_of": as_of.isoformat(),
        "scope": "Permitted 40-profile clean subset; 38 current keepers assessed and two leavers explicitly retained outside the current cohort.",
        "decision_boundary": "Evidence-led interview triage only; not a competence, eligibility or mobilisation determination.",
        "source_fingerprints": fingerprints,
        "employer_requirement_source": "employers/carrowmore-array-om-technician.md",
        "certification_definition_source": "employers/certification_schemes.json",
        "certification_schemes_loaded": [s["code"] for s in schemes],
        "summary": {
            "profiles": len(candidates),
            "current": sum(c["cohort_status"] == "current_redeployment_cohort" for c in candidates),
            "leavers": sum(c["cohort_status"] == "leaver_outside_current_cohort" for c in candidates),
            "recommend_interview": counts["recommend_interview"],
            "consider_interview": counts["consider_interview"],
            "insufficient_evidence": counts["insufficient_evidence_in_subset"],
            "outside_current_cohort": counts["outside_current_redeployment_cohort"],
        },
        "method": {
            "work_evidence": "An entry must contain an explicit maintenance action plus an electrical or mechanical plant term. Up to five diverse, highest-signal entries are shown; counts and hours are not treated as competence.",
            "recommend_interview": "At least three qualifying entries and either both electrical/mechanical coverage or explicit fault-finding evidence.",
            "consider_interview": "At least one qualifying entry but the stronger rule is not met.",
            "training": "Dated LearnHub outcome and supplied expiry are evaluated at the explicit cutoff. Pass, Attended and Not achieved remain distinct; expiry is never recomputed.",
            "height_mapping": "WAHS-1 is used as the supplied definition's direct height-safety module. This is a documented interpretation because the posting asks for a combined offshore certificate while OSSC itself has no height module.",
        },
        "candidates": candidates,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True, help="Scenario cutoff in YYYY-MM-DD format")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = build(args.source_zip.resolve(), args.as_of)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "recommendations.json"
    md_path = args.output_dir / "recommendations.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(markdown_report(payload), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "summary": payload["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
