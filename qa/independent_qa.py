#!/usr/bin/env python3
"""Independent source/output checks for the Carrowmore Array O&M submission.

This intentionally does not import the evaluator or repeat its scoring rules.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = "carrowmore-data-pack/"
EXPECTED = {
    ROOT + "clean/keepers.json": "5aa6e0a811b5d49da43d524d86023163aea90ff67db32143be1821cba554d58b",
    ROOT + "clean/logbook_entries.json": "b7b247d406d4faa538c1880991b2f85d6c1b2b9c4300a02b7834850cc9324a95",
    ROOT + "raw/training/vendor-c-learnhub-2017-2026.json": "a8d0f1a3dab7ad6f430e7352c72e434c01d8b38ca1cec3d4de26a2fdd4403c2b",
    ROOT + "employers/certification_schemes.json": "51ea3687808118b5aefe1707de26f2c87661ba20df6c542d98ac3b4f237de4ef",
    ROOT + "employers/carrowmore-array-om-technician.md": "64b86a9bafe79f01757495cbf0eebde11e0cb5f680d21928cd0cf0ecbdfa6d0c",
    ROOT + "raw/personnel/cla_personnel_export.csv": "14ba3653d9ab29b86b273cb7016dba574d840729de85d5b0eac367ed3170b4c7",
    ROOT + "raw/personnel/cla_personnel_leavers.csv": "920f7a76d3710ac08a56d7bf9ac0de83cf65f5525e8c7a1dfc905b517d2d9a0a",
    ROOT + "raw/appraisals/station_manager_notes/2011-nevisbeg-keeper-note.txt": "767fa1decaafb6e56556ca7416b069e07cebf85a2cbd5d3c2d661df85d08adc4",
    ROOT + "raw/appraisals/appraisals.jsonl": "c19ba6216619c0c4d103b5dd7d99edb49f9722fba94a6eb9de824adfba1488d1",
}
ARCHIVE_HASH = "59f12ea4dfb43d311429fdd34c207517c2ffefbf917e4cdfe9737ca5776270f5"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(zf: zipfile.ZipFile, name: str):
    return json.loads(zf.read(name).decode("utf-8"))


class Checks:
    def __init__(self):
        self.items = []

    def check(self, name: str, condition: bool, detail: str = ""):
        self.items.append({"check": name, "passed": bool(condition), "detail": detail})

    def equal(self, name: str, actual, expected):
        def stable(value):
            if isinstance(value, set):
                return repr(sorted(value))
            if isinstance(value, dict):
                return json.dumps(dict(sorted(value.items())), ensure_ascii=False, sort_keys=True)
            return repr(value)

        self.check(name, actual == expected, f"expected={stable(expected)}; actual={stable(actual)}")


def normalize_numeric_id(value: str | None) -> str | None:
    if not value:
        return None
    try:
        number = Decimal(value.strip().lstrip("'"))
    except InvalidOperation:
        return None
    return str(int(number)) if number.is_finite() and number == number.to_integral_value() else None


def normalize_name(value: str | None) -> str | None:
    if not value:
        return None
    value = unicodedata.normalize("NFKD", value)
    return "".join(c.lower() for c in value if c.isalnum() and not unicodedata.combining(c))


def canonical_work_pattern(text: str) -> str:
    """Independent normalization for superficial numeric/measurement variants."""
    value = text.lower()
    value = re.sub(
        r"\b\d+(?:\.\d+)?\s*(?:psi|bar|volts?|v|ohms?|amps?|a|hz|kw|rpm|°?c)\b",
        " measurement ",
        value,
        flags=re.I,
    )
    value = re.sub(r"\d+(?:\.\d+)?", "#", value)
    value = re.sub(r"\bno\s*\.?\s*#", "no #", value)
    return re.sub(r"\W+", " ", value).strip()


def add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def resolve_reference(zf: zipfile.ZipFile, source_reference: str, era: int) -> dict | None:
    source, locator = source_reference.split("#", 1)
    raw = zf.read(ROOT + source)
    if era == 1:
        lines = raw.decode("utf-8", errors="replace").splitlines()
        n = int(locator.removeprefix("L"))
        return {"line": n, "text": lines[n - 1], "identifier_type": "absent", "identifier": None} if 1 <= n <= len(lines) else None
    if era == 2:
        for line in raw.decode("cp1252", errors="replace").splitlines():
            if line.startswith(locator + "|"):
                f = line.split("|")
                return {"record_id": f[0], "keeper_code": f[3], "activity": f[6], "identifier_type": "keeper_code", "identifier": f[3]}
        return None
    lines = raw.decode("utf-8-sig", errors="replace").splitlines()
    n = int(locator)
    if not (2 <= n <= len(lines)):
        return None
    header = [value.strip().lower() for value in next(csv.reader([lines[0]]))]
    row = next(csv.reader([lines[n - 1]]))
    values = dict(zip(header, row))
    if "keeper_id" in values:
        identifier_type, identifier = "payroll_reference", values["keeper_id"]
    elif "keeper name" in values:
        identifier_type, identifier = "name", values["keeper name"]
    else:
        identifier_type, identifier = "absent", None
    return {
        "row": n,
        "identifier_type": identifier_type,
        "identifier": identifier,
        "activity": values.get("description", values.get("activity", "")).lstrip("'"),
    }


def has_conflict(candidate: dict, code: str, scheme: str | None = None) -> bool:
    return any(c["code"] == code and (scheme is None or c.get("scheme") == scheme) for c in candidate["credential_conflicts"])


def run(zip_path: Path, results_path: Path) -> dict:
    checks = Checks()
    results_bytes = results_path.read_bytes()
    output = json.loads(results_bytes.decode("utf-8"))
    with zipfile.ZipFile(zip_path) as zf:
        checks.equal("archive SHA-256", digest(zip_path.read_bytes()), ARCHIVE_HASH)
        checks.equal("archive member count", len(zf.namelist()), 1447)
        for member, expected in EXPECTED.items():
            checks.equal(f"member SHA-256: {member.removeprefix(ROOT)}", digest(zf.read(member)), expected)

        keepers = load_json(zf, ROOT + "clean/keepers.json")
        logs = load_json(zf, ROOT + "clean/logbook_entries.json")
        appraisals = [
            json.loads(line)
            for line in zf.read(ROOT + "raw/appraisals/appraisals.jsonl").decode("utf-8").splitlines()
            if line.strip()
        ]
        learnhub = load_json(zf, ROOT + "raw/training/vendor-c-learnhub-2017-2026.json")["records"]
        schemes = load_json(zf, ROOT + "employers/certification_schemes.json")["schemes"]
        posting_text = zf.read(ROOT + "employers/carrowmore-array-om-technician.md").decode("utf-8", errors="replace")
        current_rows = list(csv.DictReader(io.StringIO(zf.read(ROOT + "raw/personnel/cla_personnel_export.csv").decode("utf-8-sig"))))
        leaver_rows = list(csv.DictReader(io.StringIO(zf.read(ROOT + "raw/personnel/cla_personnel_leavers.csv").decode("utf-8-sig"))))
        logs_by_id = {r["entry_id"]: r for r in logs}
        appraisals_by_id = {r["record_id"]: r for r in appraisals}
        training_by_id = {r["id"]: r for r in learnhub}
        candidates = {r["keeper_code"]: r for r in output["candidates"]}
        keepers_by_id = {r["keeper_code"]: r for r in keepers}
        scheme_map = {s["code"]: s for s in schemes}

        checks.equal("explicit scenario date", output["as_of"], "2026-10-11")
        checks.equal("40 unique output profiles", len(candidates), 40)
        checks.equal("output IDs equal clean-subset IDs", set(candidates), set(keepers_by_id))
        checks.equal("clean cohort split", Counter(k["status"] for k in keepers), Counter({"current": 38, "left": 2}))
        checks.equal("output cohort split", Counter(c["cohort_status"] for c in candidates.values()), Counter({"current_redeployment_cohort": 38, "leaver_outside_current_cohort": 2}))
        checks.check("all clean current IDs occur in current personnel export", all(k["keeper_code"] in {r["keeper_code"] for r in current_rows} for k in keepers if k["status"] == "current"))
        checks.check("all clean leaver IDs occur in leavers export", all(k["keeper_code"] in {r["keeper_code"] for r in leaver_rows} for k in keepers if k["status"] == "left"))

        evidence_count = 0
        for candidate in candidates.values():
            checks.equal(f"candidate as-of: {candidate['keeper_code']}", candidate["as_of"], "2026-10-11")
            for evidence in candidate["relevant_experience"]:
                evidence_count += 1
                source = logs_by_id.get(evidence["entry_id"])
                checks.check(f"evidence ID exists: {evidence['entry_id']}", source is not None)
                if source:
                    checks.equal(f"evidence keeper: {evidence['entry_id']}", source["keeper_code"], candidate["keeper_code"])
                    checks.equal(f"evidence exact text: {evidence['entry_id']}", evidence["text"], source["text"])
                    checks.equal(f"evidence exact date: {evidence['entry_id']}", evidence["date"], source["date"])
                    checks.equal(f"evidence source ref: {evidence['entry_id']}", evidence["source_reference"], source["source_record"])
                    checks.check(f"evidence not future: {evidence['entry_id']}", date.fromisoformat(evidence["date"]) <= date(2026, 10, 11))
                    resolved = resolve_reference(zf, source["source_record"], source["source_era"])
                    checks.check(f"raw citation resolves: {evidence['entry_id']}", resolved is not None)
                    if resolved:
                        provenance = evidence["raw_corroboration"]["identity_provenance"]
                        checks.equal(f"identity type preserved: {evidence['entry_id']}", provenance["identifier_type"], resolved["identifier_type"])
                        checks.equal(f"raw identifier preserved: {evidence['entry_id']}", provenance["raw_value"], resolved["identifier"])
                        if resolved["identifier_type"] == "keeper_code":
                            expected_match = resolved["identifier"] == source["keeper_code"]
                            checks.equal(f"DAT attribution status preserved: {evidence['entry_id']}", provenance["corroboration"], "corroborates" if expected_match else "conflicts")
                        elif resolved["identifier_type"] == "payroll_reference":
                            expected_payroll = keepers_by_id[source["keeper_code"]]["payroll_ref"]
                            checks.equal(f"payroll normalization: {evidence['entry_id']}", provenance["normalized_raw_value"], normalize_numeric_id(resolved["identifier"]))
                            checks.equal(f"clean payroll preserved: {evidence['entry_id']}", provenance["expected_value"], expected_payroll)
                            expected_match = normalize_numeric_id(resolved["identifier"]) == normalize_numeric_id(expected_payroll)
                            checks.equal(f"payroll corroboration status: {evidence['entry_id']}", provenance["corroboration"], "corroborates" if expected_match else "conflicts")
                        elif resolved["identifier_type"] == "name":
                            expected_names = {normalize_name(keepers_by_id[source["keeper_code"]].get("name")), normalize_name(keepers_by_id[source["keeper_code"]].get("name_ascii"))}
                            expected_match = normalize_name(resolved["identifier"]) in expected_names
                            checks.equal(f"name corroboration status: {evidence['entry_id']}", provenance["corroboration"], "corroborates" if expected_match else "conflicts")
                        else:
                            checks.equal(f"absent raw identity retained: {evidence['entry_id']}", provenance["corroboration"], "absent")
        checks.check("at least one traceable work example emitted", evidence_count > 0, f"evidence_count={evidence_count}")

        # Prepared case 1: expired prerequisite remains visible; summary is not silently accepted.
        lh500938 = training_by_id["LH500938"]
        checks.equal("QA1 LH500938 belongs to K0589", lh500938["keeper_code"], "K0589")
        checks.equal("QA1 LH500938 is OSSC-SS", lh500938["scheme_module"], "OSSC-SS")
        checks.equal("QA1 LH500938 supplied expiry", lh500938["expires_on"], "2023-05-09")
        checks.check("QA1 K0589 prerequisite conflict", has_conflict(candidates["K0589"], "prerequisite_not_established", "SMOC"))
        checks.check("QA1 expired pass shown", any(c["record_id"] == "LH500938" and c["status_at_cutoff"] == "pass_expired" for c in candidates["K0589"]["credential_claims"]))

        # Prepared case 2: valid aggregate SMOC does not create an OSSC-SS pass.
        k1446_raw_ss = [r for r in learnhub if r["keeper_code"] == "K1446" and r["scheme_module"] == "OSSC-SS" and r["outcome"] == "Pass"]
        checks.equal("QA2 K1446 has no supplied OSSC-SS Pass", len(k1446_raw_ss), 0)
        checks.check("QA2 K1446 prerequisite not established", has_conflict(candidates["K1446"], "prerequisite_not_established", "SMOC"))

        # Prepared case 3: exact LOSC sequence is shown as unresolved chronology.
        losc_expected = {
            "LH502309": ("LOSC-A", "2023-02-04"),
            "LH502310": ("LOSC-P", "2024-04-16"),
            "LH502318": ("LOSC-S", "2025-05-03"),
        }
        for rid, expected in losc_expected.items():
            checks.equal(f"QA3 {rid} module/date", (training_by_id[rid]["scheme_module"], training_by_id[rid]["completed_on"]), expected)
        checks.check("QA3 K1200 prerequisite chronology not established", has_conflict(candidates["K1200"], "prerequisite_chronology_not_established", "LOSC"))

        # Prepared cases 4 and 5 test outcome/expiry semantics independently of subset membership.
        checks.equal("QA4 preserve LH500001 supplied expiry", training_by_id["LH500001"]["expires_on"], "2022-07-14")
        checks.equal("QA5 preserve LH500002 outcome", training_by_id["LH500002"]["outcome"], "Not achieved")

        # Prepared case 6: future record is listed but not used as a current claim.
        future = training_by_id["LH502324"]
        checks.equal("QA6 future record date", future["completed_on"], "2026-11-23")
        checks.check("QA6 future record separated", any(r["record_id"] == "LH502324" and r["status_at_cutoff"] == "future_at_cutoff" for r in candidates["K1200"]["future_evidence_not_used"]))
        checks.check("QA6 future record absent from current claims", all(r["record_id"] != "LH502324" for r in candidates["K1200"]["credential_claims"]))

        # Prepared case 7: Oileann evidence is exact and never becomes authorisation.
        cl006360 = logs_by_id["CL006360"]
        supp = candidates["K1538"]["supplementary_evidence"]
        checks.equal("QA7 CL006360 keeper", cl006360["keeper_code"], "K1538")
        checks.check("QA7 11kV evidence surfaced", any(s.get("supporting_entry", {}).get("entry_id") == "CL006360" for s in supp))
        note_lines = zf.read(ROOT + "raw/appraisals/station_manager_notes/2011-nevisbeg-keeper-note.txt").decode("utf-8", errors="replace").splitlines()
        checks.check("QA7 note identifies NI GHARBHAIL O", "NI GHARBHAIL O" in note_lines[2])
        checks.check("QA7 note records generator-control fault finding", "generator control gear" in note_lines[8])
        checks.check("QA7 note records HV switching", "high voltage switching" in note_lines[10])
        checks.equal("QA7 exact note citation", supp[0]["source_reference"], "raw/appraisals/station_manager_notes/2011-nevisbeg-keeper-note.txt#L3,L7,L9,L11")
        hand_entry = supp[0]["supporting_entry"]
        checks.equal("QA7 CL006360 exact text", hand_entry["text"], cl006360["text"])
        checks.equal("QA7 CL006360 exact source", hand_entry["source_reference"], cl006360["source_record"])
        checks.check("QA7 CL006360 raw citation resolves", resolve_reference(zf, cl006360["source_record"], 2) is not None)
        checks.check("QA7 authorisation explicitly not established", any(x["code"] == "authorization_not_established" for x in candidates["K1538"]["limitations"]))

        # Prepared case 8: stages are consecutive from one, not inferred from later modules.
        k0561_completed = {r["module"] for r in keepers_by_id["K0561"]["training_records"] if r["scheme"] == "MECS" and r["outcome"] == "completed"}
        checks.check("QA8 K0561 lacks MECS-1", "MECS-1" not in k0561_completed)
        checks.check("QA8 K0561 stage conflict", has_conflict(candidates["K0561"], "consecutive_stage_not_established", "MECS"))

        # Prepared case 9: leavers never enter the current recommendation cohort.
        for kid in ("K1203", "K1458"):
            checks.equal(f"QA9 {kid} cohort", candidates[kid]["cohort_status"], "leaver_outside_current_cohort")
            checks.equal(f"QA9 {kid} recommendation", candidates[kid]["interview_recommendation"], "outside_current_redeployment_cohort")

        # Prepared case 10: exercise and assert every citation convention.
        era_examples = {1: None, 2: None, 3: None}
        for row in logs:
            if era_examples[row["source_era"]] is None:
                era_examples[row["source_era"]] = row
        for era, row in era_examples.items():
            resolved = resolve_reference(zf, row["source_record"], era)
            checks.check(f"QA10 era {era} citation resolves", resolved is not None, row["source_record"])
        checks.check("QA10 CSV locator counts header", "#8" in logs_by_id["CL006659"]["source_record"] and resolve_reference(zf, logs_by_id["CL006659"]["source_record"], 3)["row"] == 8)
        checks.check("QA10 DAT uses file and record ID", "KLOG2013.DAT#001138" in cl006360["source_record"] and resolve_reference(zf, cl006360["source_record"], 2)["record_id"] == "001138")
        checks.check("QA10 text locator uses physical line", "#L" in era_examples[1]["source_record"])

        # Correction pass 1: K1200 is assessed by the same documented rule as every current profile.
        cl005994 = logs_by_id["CL005994"]
        k1200_evidence = {row["entry_id"]: row for row in candidates["K1200"]["relevant_experience"]}
        checks.equal("Correction 1 CL005994 exact text", cl005994["text"], "Drive motor brushes and commutator dressed, rotation back to time.")
        checks.check("Correction 1 CL005994 emitted for K1200", "CL005994" in k1200_evidence)
        checks.check("Correction 1 CL005994 is electro-mechanical", {"electrical", "mechanical"} <= set(k1200_evidence["CL005994"]["categories"]))
        checks.equal("Correction 1 K1200 recommendation after appraisal reconciliation", candidates["K1200"]["interview_recommendation"], "targeted_screening_first")
        checks.check("Correction 1 K1200 reason cites own evidence", "CL005994" in candidates["K1200"]["recommendation_reason"])
        for candidate in candidates.values():
            if candidate["cohort_status"] == "current_redeployment_cohort":
                emitted_ids = {row["entry_id"] for row in candidate["relevant_experience"]}
                checks.check(f"person-specific recommendation reason: {candidate['keeper_code']}", any(entry_id in candidate["recommendation_reason"] for entry_id in emitted_ids))
                checks.equal(f"no ranking used: {candidate['keeper_code']}", candidate["recommendation_criteria"]["ranking_used"], False)

        # Correction pass 2: supplied expiry and nominal scheme-rule date both survive.
        named_expiry_cases = {
            "LH502305": ("K1200", "OSSC-SS", "2022-05-18", "2026-12-20", 4, "2026-05-18"),
            "LH502297": ("K1200", "MECS-2", "2021-02-25", "2026-11-06", 5, "2026-02-25"),
            "LH502579": ("K1345", "HVAP-04", "2023-01-14", "2026-11-04", 3, "2026-01-14"),
        }
        for record_id, expected in named_expiry_cases.items():
            keeper_code, module, completed, supplied, years, nominal = expected
            source = training_by_id[record_id]
            checks.equal(f"Correction 2 source fields {record_id}", (source["keeper_code"], source["scheme_module"], source["completed_on"], source["expires_on"]), (keeper_code, module, completed, supplied))
            claim = next(row for row in candidates[keeper_code]["credential_claims"] if row["record_id"] == record_id)
            comparison = claim["expiry_comparison"]
            checks.equal(f"Correction 2 supplied expiry preserved {record_id}", comparison["supplied_expiry"], supplied)
            checks.equal(f"Correction 2 renewal years preserved {record_id}", comparison["scheme_renewal_years"], years)
            checks.equal(f"Correction 2 nominal date {record_id}", comparison["nominal_scheme_rule_date"], nominal)
            checks.equal(f"Correction 2 unresolved cutoff status {record_id}", claim["status_at_cutoff"], "pass_expiry_conflict_at_cutoff")
            checks.check(f"Correction 2 conflict emitted {record_id}", any(c["code"] == "expiry_rule_conflict" and c.get("record_id") == record_id for c in candidates[keeper_code]["credential_conflicts"]))
            checks.check(f"Correction 2 issuer action {record_id}", any(record_id in action and "issuer" in action.lower() for action in candidates[keeper_code]["later_qualification_and_mobilisation_actions"]))

        independently_conflicting = set()
        for candidate in candidates.values():
            for claim in candidate["credential_claims"]:
                source = training_by_id[claim["record_id"]]
                module = source["scheme_module"]
                scheme = scheme_map.get(module.split("-", 1)[0])
                if source["outcome"] != "Pass" or not source.get("completed_on") or not source.get("expires_on") or not scheme or not scheme.get("renewal_years"):
                    continue
                completed = date.fromisoformat(source["completed_on"])
                supplied = date.fromisoformat(source["expires_on"])
                nominal = add_years(completed, scheme["renewal_years"])
                if completed <= date(2026, 10, 11) and (supplied >= date(2026, 10, 11)) != (nominal >= date(2026, 10, 11)):
                    independently_conflicting.add(claim["record_id"])
        emitted_conflicting = {claim["record_id"] for candidate in candidates.values() for claim in candidate["credential_claims"] if claim["status_at_cutoff"] == "pass_expiry_conflict_at_cutoff"}
        checks.equal("Correction 2 all cutoff-changing expiry conflicts found", emitted_conflicting, independently_conflicting)

        # Correction pass 3: suspect measurements remain verbatim but are not trusted numerically.
        def expected_measurement_warning(text):
            return bool(
                (re.search(r"\bmegger\b", text, re.I) and re.search(r"\b\d+(?:\.\d+)?\s*(psi|bar)\b", text, re.I))
                or (re.search(r"\bpump\b.*\bdelivery\b", text, re.I) and re.search(r"\b\d+(?:\.\d+)?\s*(V|volts?)\b", text, re.I))
                or (re.search(r"\bAVR\b", text, re.I) and re.search(r"\bvolts?\s+set\b", text, re.I) and re.search(r"\b\d+(?:\.\d+)?\s*ohms?\b", text, re.I))
            )
        for candidate in candidates.values():
            for evidence in candidate["relevant_experience"]:
                expected_warning = expected_measurement_warning(evidence["text"])
                checks.equal(f"measurement warning status: {evidence['entry_id']}", bool(evidence["measurement_quality_flags"]), expected_warning)
                if expected_warning:
                    checks.check(f"measurement quote preserved: {evidence['entry_id']}", evidence["text"] == logs_by_id[evidence["entry_id"]]["text"])
                    checks.check(f"measurement not treated as reliable: {evidence['entry_id']}", all("unreliable" in flag["finding"] for flag in evidence["measurement_quality_flags"]))
        emitted_measurement_warnings = [
            row
            for candidate in candidates.values()
            for row in candidate["relevant_experience"]
            if row["measurement_quality_flags"]
        ]
        checks.check("Correction 3 retained unit anomalies remain warned", bool(emitted_measurement_warnings))
        checks.check(
            "Correction 3 retained warning types remain explicit",
            all(flag["code"] == "inconsistent_measurement_unit" for row in emitted_measurement_warnings for flag in row["measurement_quality_flags"]),
        )

        # Correction pass 4: scientific payroll notation is normalized, not guessed.
        cl010280 = logs_by_id["CL010280"]
        raw_10280 = resolve_reference(zf, cl010280["source_record"], 3)
        out_10280 = next(row for row in candidates["K0147"]["relevant_experience"] if row["entry_id"] == "CL010280")
        provenance_10280 = out_10280["raw_corroboration"]["identity_provenance"]
        checks.equal("Correction 4 raw scientific payroll", raw_10280["identifier"], "1.1245E+04")
        checks.equal("Correction 4 normalized scientific payroll", normalize_numeric_id(raw_10280["identifier"]), "11245")
        checks.equal("Correction 4 clean payroll", keepers_by_id["K0147"]["payroll_ref"], "0011245")
        checks.equal("Correction 4 payroll provenance", provenance_10280["corroboration"], "corroborates")

        # Correction pass 5: retain Oileann testimony while exposing its chronology conflict.
        k1538 = keepers_by_id["K1538"]
        checks.equal("Correction 5 K1538 recorded join", k1538["date_joined"], "1998-01-01")
        nev_posting = next(posting for posting in k1538["postings"] if posting["station_code"] == "NEV")
        checks.equal("Correction 5 K1538 Nevisbeg begins", nev_posting["from_year"], 2009)
        checks.check("Correction 5 note claims eleven years", "eleven years" in note_lines[6])
        chronology = candidates["K1538"]["identity_and_chronology_conflicts"]
        checks.check("Correction 5 chronology conflict emitted", any(row["code"] == "oileann_station_tenure_conflict" for row in chronology))
        checks.check("Correction 5 current authorization not inferred", any(row["code"] == "authorization_not_established" for row in candidates["K1538"]["limitations"]))

        # Correction passes 6 and 7: leavers stop, while current action dependencies are ordered.
        checks.check("Correction 7 employer source funds renewals", "We will pay for renewals but we cannot mobilise you without one." in posting_text)
        for keeper_code in ("K1203", "K1458"):
            candidate = candidates[keeper_code]
            checks.equal(f"Correction 6 no leaver requirements {keeper_code}", candidate["remaining_requirements"], [])
            checks.equal(f"Correction 6 no leaver mobilisation assessment {keeper_code}", candidate["mobilisation_readiness"], "not_assessed_outside_current_cohort")
            checks.equal(f"Correction 6 leaver stop action {keeper_code}", candidate["next_actions"], ["No current redeployment pathway is assessed for this leaver."])
        for candidate in candidates.values():
            if candidate["cohort_status"] != "current_redeployment_cohort":
                continue
            initial = candidate["initial_selection_actions"]
            actions = candidate["later_qualification_and_mobilisation_actions"]
            checks.equal(f"Correction 7 initial action count {candidate['keeper_code']}", len(initial), 1)
            checks.equal(f"Correction 7 later action count {candidate['keeper_code']}", len(actions), 7)
            checks.check(f"Correction 7 qualification conditional {candidate['keeper_code']}", actions[0].startswith("Only if the initial selection outcome"))
            checks.check(f"Correction 7 verification before courses {candidate['keeper_code']}", actions[1].startswith("First,"))
            checks.check(f"Correction 7 willingness before courses {candidate['keeper_code']}", actions[2].startswith("Confirm directly"))
            checks.check(f"Correction 7 medical before OSSC {candidate['keeper_code']}", actions[3].startswith("Obtain a current offshore medical"))
            checks.check(f"Correction 7 module-specific OSSC {candidate['keeper_code']}", actions[4].startswith("After medical clearance") and all(module in actions[4] for module in ("OSSC-SS", "OSSC-FF", "OSSC-FA")))
            checks.check(f"Correction 7 OSSC precedes WAHS {candidate['keeper_code']}", actions[5].startswith("After OSSC-SS is issuer-verified current") and "WAHS-1" in actions[5])
            checks.check(f"Correction 7 funding limits {candidate['keeper_code']}", "first-time funding is not promised" in (actions[4] + actions[5]) or "employer funds renewals" in (actions[4] + actions[5]) or "present and issuer-verify" in (actions[4] + actions[5]))
            checks.check(f"Correction 7 assessment last {candidate['keeper_code']}", actions[6].startswith("Finally,"))

        # Decision-quality correction: appraisal attribution and full-history review.
        clean_current_ids = {row["keeper_code"] for row in keepers if row["status"] == "current"}
        keyed_appraisals = [row for row in appraisals if row.get("keeper_code")]
        current_appraisals = [row for row in keyed_appraisals if row["keeper_code"] in clean_current_ids]
        checks.equal("appraisal source row count", len(appraisals), 4422)
        checks.equal("appraisal keyed row count", len(keyed_appraisals), 2694)
        checks.equal("appraisal null-key rows left unattached", sum(not row.get("keeper_code") for row in appraisals), 1728)
        checks.equal("current-cohort keyed appraisal rows reviewed", len(current_appraisals), 305)
        checks.equal("current profiles with keyed appraisals", len({row["keeper_code"] for row in current_appraisals}), 37)
        checks.equal("output current appraisal reviewed count", output["summary"]["appraisal_rows_reviewed_for_current_cohort"], 305)
        checks.equal("K0310 has no keyed appraisal", candidates["K0310"]["appraisal_review"]["reviewed_record_ids"], [])

        logs_by_keeper = {}
        for row in logs:
            logs_by_keeper.setdefault(row["keeper_code"], []).append(row)
        appraisals_by_keeper = {}
        for row in current_appraisals:
            appraisals_by_keeper.setdefault(row["keeper_code"], []).append(row)
        for keeper_code in sorted(clean_current_ids):
            candidate = candidates[keeper_code]
            source_logs = logs_by_keeper.get(keeper_code, [])
            review = candidate["work_history_review"]
            checks.equal(f"full log row count reviewed: {keeper_code}", review["source_entry_count"], len(source_logs))
            checks.equal(f"cutoff log row count reviewed: {keeper_code}", review["entries_at_or_before_cutoff"], sum(date.fromisoformat(row["date"]) <= date(2026, 10, 11) for row in source_logs))
            checks.equal(f"full history flag: {keeper_code}", review["full_clean_history_reviewed"], True)

            source_rows = sorted(appraisals_by_keeper.get(keeper_code, []), key=lambda row: (row["year"], row["record_id"]))
            appraisal_review = candidate["appraisal_review"]
            checks.equal(f"exact keyed appraisal IDs reviewed: {keeper_code}", appraisal_review["reviewed_record_ids"], [row["record_id"] for row in source_rows])
            checks.equal(f"keyed appraisal count reviewed: {keeper_code}", appraisal_review["keyed_rows_reviewed"], len(source_rows))
            checks.equal(f"same-year appraisal IDs: {keeper_code}", appraisal_review["same_year_record_ids_timing_uncertain"], [row["record_id"] for row in source_rows if row["year"] == 2026])
            checks.equal(f"future-year appraisal IDs: {keeper_code}", appraisal_review["future_year_record_ids_not_used"], [row["record_id"] for row in source_rows if row["year"] > 2026])
            for item in appraisal_review["role_relevant_testimony"]:
                source = appraisals_by_id[item["record_id"]]
                checks.equal(f"appraisal exact keeper key: {item['record_id']}", source["keeper_code"], keeper_code)
                checks.equal(f"appraisal exact year: {item['record_id']}", item["year"], source["year"])
                checks.equal(f"appraisal year precision: {item['record_id']}", item["date_precision"], "year")
                checks.equal(f"appraisal exact station: {item['record_id']}", item["station_code"], source["station"])
                checks.equal(f"appraisal source reference: {item['record_id']}", item["source_reference"], f"raw/appraisals/appraisals.jsonl#{item['record_id']}")
                checks.equal(f"appraisal full-text hash: {item['record_id']}", item["source_text_sha256"], digest(source["text"].encode("utf-8")))
                checks.check(f"appraisal excerpts exact: {item['record_id']}", bool(item["role_relevant_excerpt"]) and all(excerpt in source["text"] for excerpt in item["role_relevant_excerpt"]))
                checks.check(f"appraisal omits irrelevant identity fields: {item['record_id']}", "manager" not in item and "keeper_name" not in item)
                if source["year"] == 2026:
                    checks.equal(f"same-year appraisal context only: {item['record_id']}", item["decision_time_treatment"], "same_year_timing_uncertain_context_only")

        allowed_decisions = {
            "supported_technical_interview",
            "targeted_screening_first",
            "insufficient_evidence",
            "outside_current_redeployment_cohort",
        }
        checks.check("only bounded non-ranking decisions emitted", all(row["interview_recommendation"] in allowed_decisions for row in candidates.values()))
        checks.equal("decision summary matches profiles", Counter(row["interview_recommendation"] for row in candidates.values()), Counter({
            "supported_technical_interview": output["summary"]["supported_technical_interview"],
            "targeted_screening_first": output["summary"]["targeted_screening_first"],
            "insufficient_evidence": output["summary"]["insufficient_evidence"],
            "outside_current_redeployment_cohort": output["summary"]["outside_current_cohort"],
        }))

        named_appraisal_cases = {
            "AP003496": ("K1200", "has not, to my knowledge, carried out any of the plant work"),
            "AP001433": ("K0561", "Needs supervision on pumped systems."),
            "AP003571": ("K1231", "switchgear work has to be checked behind her."),
            "AP004150": ("K1446", "Needs supervision on the standby banks."),
            "AP004147": ("K1446", "The standard achieved in height work falls below that expected of the grade."),
        }
        for record_id, (keeper_code, exact_fragment) in named_appraisal_cases.items():
            source = appraisals_by_id[record_id]
            checks.equal(f"named appraisal keeper: {record_id}", source["keeper_code"], keeper_code)
            checks.check(f"named appraisal exact text: {record_id}", exact_fragment in source["text"])
            checks.check(f"named appraisal surfaced as concern: {record_id}", record_id in candidates[keeper_code]["appraisal_review"]["material_pre_cutoff_concern_ids"])
            checks.equal(f"named appraisal drives targeted screen: {record_id}", candidates[keeper_code]["interview_recommendation"], "targeted_screening_first")

        k1200_material = {"CL005994", "CL007505", "CL009097", "CL009921"}
        checks.check("K1200 all named material logs shown", k1200_material <= {row["entry_id"] for row in candidates["K1200"]["relevant_experience"]})
        checks.check("K1200 reason reconciles log and appraisal", "CL005994" in candidates["K1200"]["recommendation_reason"] and "AP003496" in candidates["K1200"]["recommendation_reason"])
        checks.equal("K0586 cautious targeted screen", candidates["K0586"]["interview_recommendation"], "targeted_screening_first")
        checks.equal("K0586 distinct evidence independently visible", candidates["K0586"]["work_history_review"]["distinct_qualifying_examples"], 3)

        mixed = next(item for item in candidates["K1231"]["appraisal_review"]["role_relevant_testimony"] if item["record_id"] == "AP003571")
        checks.check("K1231 mixed support and concern preserved", bool(mixed["support_signals"]) and bool(mixed["concern_signals"]))
        for keeper_code, record_id in (("K0371", "AP000798"), ("K0847", "AP002309")):
            candidate = candidates[keeper_code]
            checks.equal(f"{keeper_code} supported technical interview", candidate["interview_recommendation"], "supported_technical_interview")
            checks.check(f"{keeper_code} manager testimony distinguished", record_id in candidate["appraisal_review"]["strong_manager_support_ids"] and record_id in candidate["recommendation_reason"])

        markdown_path = results_path.with_suffix(".md")
        checks.check("readable recommendations exist", markdown_path.is_file())
        if markdown_path.is_file():
            markdown = markdown_path.read_text(encoding="utf-8")
            checks.check("comparison table precedes details", markdown.find("## Current-keeper comparison") < markdown.find("## Detailed evidence"))
            checks.equal("comparison table has 38 current rows", sum(line.startswith("| K") for line in markdown.splitlines()), 38)

            # Repair 1: every retained record must occur in its own detailed
            # profile, not merely in the summary table or another profile.
            for candidate in candidates.values():
                heading = rf"^## {re.escape(candidate['keeper_code'])} — .*$"
                match = re.search(heading, markdown, flags=re.M)
                checks.check(f"Markdown profile section exists: {candidate['keeper_code']}", match is not None)
                if not match:
                    continue
                next_heading = re.search(r"^## K\d+ — .*$", markdown[match.end():], flags=re.M)
                section_end = match.end() + next_heading.start() if next_heading else len(markdown)
                section = markdown[match.start():section_end]
                for evidence in candidate["relevant_experience"]:
                    checks.check(
                        f"Markdown retained experience in own section: {evidence['entry_id']}",
                        all(value in section for value in (evidence["entry_id"], evidence["date"], evidence["text"], evidence["source_reference"])),
                    )
                    provenance = evidence["raw_corroboration"]["identity_provenance"]
                    checks.check(
                        f"Markdown attribution in own section: {evidence['entry_id']}",
                        provenance["corroboration"] in section or "clean/manual attribution" in section,
                    )
                    for flag in evidence["measurement_quality_flags"]:
                        checks.check(
                            f"Markdown measurement warning in own section: {evidence['entry_id']}",
                            flag["code"] in section and flag["observed"] in section,
                        )

        # Repair 2: value/unit variants canonicalize together, while K1200's
        # four display exceptions remain visible without ID-based identities.
        measurement_variants = [logs_by_id[entry_id]["text"] for entry_id in ("CL006460", "CL007701", "CL009081")]
        checks.equal(
            "measurement value/unit variants share one canonical pattern",
            len({canonical_work_pattern(text) for text in measurement_variants}),
            1,
        )
        k1200 = candidates["K1200"]
        k1200_review = k1200["work_history_review"]
        checks.equal("K1200 canonical pattern count", k1200_review["distinct_qualifying_examples"], 3)
        checks.equal("K1200 count equals unique canonical keys", k1200_review["distinct_qualifying_examples"], len(set(k1200_review["canonical_pattern_keys"])))
        checks.check("K1200 canonical keys contain no display IDs", all(not key.startswith("material:") and "CL00" not in key for key in k1200_review["canonical_pattern_keys"]))
        checks.check("K1200 four display exceptions retained", {"CL005994", "CL007505", "CL009097", "CL009921"} <= set(k1200_review["displayed_entry_ids"]))
        for evidence in k1200["relevant_experience"]:
            checks.equal(f"K1200 displayed record uses canonical text key: {evidence['entry_id']}", evidence["template_key"], canonical_work_pattern(logs_by_id[evidence["entry_id"]]["text"]))
        checks.check("K1200 display-only mercury record not counted as canonical decision pattern", canonical_work_pattern(logs_by_id["CL009921"]["text"]) not in k1200_review["canonical_pattern_keys"])

        # Repair 3: no matched dated Pass is an evidence gap, not proof that
        # training is needed. Verification must precede the conditional course.
        essential_modules = ("OSSC-SS", "OSSC-FF", "OSSC-FA", "WAHS-1")
        absent_action_checks = 0
        for candidate in candidates.values():
            if candidate["cohort_status"] != "current_redeployment_cohort":
                continue
            actions = " ".join(candidate["later_qualification_and_mobilisation_actions"])
            recorded_modules = {claim["module"] for claim in candidate["credential_claims"]}
            for module in essential_modules:
                if module in recorded_modules:
                    continue
                absent_action_checks += 1
                module_start = actions.find(f"{module}:")
                checks.check(f"absent module action present: {candidate['keeper_code']}/{module}", module_start >= 0)
                if module_start >= 0:
                    module_text = actions[module_start:]
                    next_module = re.search(r"\s(?:OSSC-(?:SS|FF|FA)|WAHS-1):", module_text[len(module) + 1:])
                    if next_module:
                        module_text = module_text[: len(module) + 1 + next_module.start()]
                    checks.check(
                        f"absent module verifies before conditional training: {candidate['keeper_code']}/{module}",
                        "first verify any existing certificate with the issuer" in module_text
                        and "Only if current required coverage remains unestablished" in module_text
                        and module_text.index("first verify") < module_text.index("Only if"),
                    )
        checks.check("absent-record action cases exercised", absent_action_checks > 0, f"cases={absent_action_checks}")

        # Repair 4: named appraisal context is exact and decision-neutral.
        named_context = {
            "AP000090": ("K0147", "There is a habit of mind here that is worth writing down: Coilean will not leave rope work half done."),
            "AP000752": ("K0354", "The standard achieved in defect reporting falls below that expected of the grade."),
            "AP000753": ("K0354", "The standard achieved in inspection reports falls below that expected of the grade."),
        }
        for record_id, (keeper_code, exact_excerpt) in named_context.items():
            candidate = candidates[keeper_code]
            selected = next((item for item in candidate["appraisal_review"]["role_relevant_testimony"] if item["record_id"] == record_id), None)
            checks.check(f"named appraisal context retained: {record_id}", selected is not None)
            if selected:
                checks.check(f"named appraisal context exact: {record_id}", exact_excerpt in selected["role_relevant_excerpt"] and exact_excerpt in appraisals_by_id[record_id]["text"])
                checks.equal(f"named appraisal source hash exact: {record_id}", selected["source_text_sha256"], digest(appraisals_by_id[record_id]["text"].encode("utf-8")))
            checks.check(f"named appraisal context does not alter material concern gate: {record_id}", record_id not in candidate["appraisal_review"]["material_pre_cutoff_concern_ids"])
        for candidate in candidates.values():
            review = candidate["appraisal_review"]
            checks.equal(f"unmatched appraisal label: {candidate['keeper_code']}", review["unmatched_row_label"], "not selected by the appraisal filter")
            checks.equal(
                f"unmatched appraisal filter count: {candidate['keeper_code']}",
                review["rows_not_selected_by_appraisal_filter"],
                review["keyed_rows_reviewed"] - review["role_relevant_testimony_count"],
            )

        # Definitions must retain the source conflict: height is WAHS, not an invented OSSC module.
        checks.check("OSSC definition has no height module", all("height" not in m["name"].lower() for m in scheme_map["OSSC"]["modules"]))
        checks.check("WAHS definition contains height module", any(m["code"] == "WAHS-1" for m in scheme_map["WAHS"]["modules"]))

    failed = [item for item in checks.items if not item["passed"]]
    return {
        "schema_version": 3,
        "independence": "Reads the ZIP, appraisal JSONL and generated outputs directly; does not import evaluator code or recompute its recommendation policy.",
        "source_archive_sha256": digest(zip_path.read_bytes()),
        "recommendations_sha256": digest(results_bytes),
        "checks": len(checks.items),
        "passed": len(checks.items) - len(failed),
        "failed": len(failed),
        "status": "PASS" if not failed else "FAIL",
        "failures": failed,
        "prepared_case_count": 10,
        "details": checks.items,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args.source_zip.resolve(), args.results.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "checks", "passed", "failed", "recommendations_sha256")}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
