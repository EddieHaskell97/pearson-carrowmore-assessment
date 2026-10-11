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
        learnhub = load_json(zf, ROOT + "raw/training/vendor-c-learnhub-2017-2026.json")["records"]
        schemes = load_json(zf, ROOT + "employers/certification_schemes.json")["schemes"]
        posting_text = zf.read(ROOT + "employers/carrowmore-array-om-technician.md").decode("utf-8", errors="replace")
        current_rows = list(csv.DictReader(io.StringIO(zf.read(ROOT + "raw/personnel/cla_personnel_export.csv").decode("utf-8-sig"))))
        leaver_rows = list(csv.DictReader(io.StringIO(zf.read(ROOT + "raw/personnel/cla_personnel_leavers.csv").decode("utf-8-sig"))))
        logs_by_id = {r["entry_id"]: r for r in logs}
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
        checks.equal("Correction 1 K1200 recommendation", candidates["K1200"]["interview_recommendation"], "recommend_interview")
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
            checks.check(f"Correction 2 issuer action {record_id}", record_id in candidates[keeper_code]["next_actions"][0] and "issuer" in candidates[keeper_code]["next_actions"][0].lower())

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
        for entry_id in ("CL009081", "CL007341", "CL008058"):
            emitted = next(row for candidate in candidates.values() for row in candidate["relevant_experience"] if row["entry_id"] == entry_id)
            checks.check(f"Correction 3 representative unit warning {entry_id}", bool(emitted["measurement_quality_flags"]))

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
            actions = candidate["next_actions"]
            checks.equal(f"Correction 7 ordered action count {candidate['keeper_code']}", len(actions), 6)
            checks.check(f"Correction 7 verification first {candidate['keeper_code']}", actions[0].startswith("First,"))
            checks.check(f"Correction 7 willingness before courses {candidate['keeper_code']}", actions[1].startswith("Before arranging courses"))
            checks.check(f"Correction 7 medical third {candidate['keeper_code']}", actions[2].startswith("Then obtain a current offshore medical"))
            checks.check(f"Correction 7 medical precedes OSSC {candidate['keeper_code']}", actions[3].startswith("After medical clearance"))
            checks.check(f"Correction 7 OSSC precedes WAHS {candidate['keeper_code']}", actions[4].startswith("After OSSC-SS is verified current"))
            checks.check(f"Correction 7 employer renewal funding {candidate['keeper_code']}", "employer will pay for renewals" in actions[3] or "present original current" in actions[3])
            checks.check(f"Correction 7 assessment last {candidate['keeper_code']}", actions[5].startswith("Finally,"))

        # Definitions must retain the source conflict: height is WAHS, not an invented OSSC module.
        checks.check("OSSC definition has no height module", all("height" not in m["name"].lower() for m in scheme_map["OSSC"]["modules"]))
        checks.check("WAHS definition contains height module", any(m["code"] == "WAHS-1" for m in scheme_map["WAHS"]["modules"]))

    failed = [item for item in checks.items if not item["passed"]]
    return {
        "schema_version": 2,
        "independence": "Reads the ZIP and generated JSON directly; does not import evaluator code or recompute its recommendation score.",
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
