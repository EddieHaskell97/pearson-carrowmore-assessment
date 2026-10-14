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
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = "carrowmore-data-pack/"
KEEPERS = ROOT + "clean/keepers.json"
LOGS = ROOT + "clean/logbook_entries.json"
LEARNHUB = ROOT + "raw/training/vendor-c-learnhub-2017-2026.json"
SCHEMES = ROOT + "employers/certification_schemes.json"
POSTING = ROOT + "employers/carrowmore-array-om-technician.md"
HVAP_POSTING = ROOT + "employers/carrowmore-array-hv-authorised-person.md"
CURRENT = ROOT + "raw/personnel/cla_personnel_export.csv"
LEAVERS = ROOT + "raw/personnel/cla_personnel_leavers.csv"
OILEANN_NOTE = ROOT + "raw/appraisals/station_manager_notes/2011-nevisbeg-keeper-note.txt"
OSSIAN_NOTE = ROOT + "raw/appraisals/station_manager_notes/2017-raheenvarra-o-raghnaill.txt"
AOIFE_NOTE = ROOT + "raw/appraisals/station_manager_notes/2003-portnalee-ni-mhurchu.txt"
GEARALT_NOTE = ROOT + "raw/appraisals/station_manager_notes/1993-cnoclia-o-heidhneain.txt"
APPRAISALS = ROOT + "raw/appraisals/appraisals.jsonl"

EXPECTED_ARCHIVE_HASH = "59f12ea4dfb43d311429fdd34c207517c2ffefbf917e4cdfe9737ca5776270f5"
EXPECTED_MEMBER_HASHES = {
    KEEPERS: "5aa6e0a811b5d49da43d524d86023163aea90ff67db32143be1821cba554d58b",
    LOGS: "b7b247d406d4faa538c1880991b2f85d6c1b2b9c4300a02b7834850cc9324a95",
    LEARNHUB: "a8d0f1a3dab7ad6f430e7352c72e434c01d8b38ca1cec3d4de26a2fdd4403c2b",
    SCHEMES: "51ea3687808118b5aefe1707de26f2c87661ba20df6c542d98ac3b4f237de4ef",
    POSTING: "64b86a9bafe79f01757495cbf0eebde11e0cb5f680d21928cd0cf0ecbdfa6d0c",
    HVAP_POSTING: "0a2fff04396dd62d10defa122014dff1671ab04bfea4f8780241130636f66aa7",
    CURRENT: "14ba3653d9ab29b86b273cb7016dba574d840729de85d5b0eac367ed3170b4c7",
    LEAVERS: "920f7a76d3710ac08a56d7bf9ac0de83cf65f5525e8c7a1dfc905b517d2d9a0a",
    OILEANN_NOTE: "767fa1decaafb6e56556ca7416b069e07cebf85a2cbd5d3c2d661df85d08adc4",
    OSSIAN_NOTE: "73bc6dcec14edcc1b42e803c904ca086a714be12b5075793e25d9fa89a18137b",
    AOIFE_NOTE: "33d00afd7dc17fc35c297e429fbc31320296dc4147daf2043da961d9abe4168a",
    GEARALT_NOTE: "d0a5b692ea7d327981725628c0301c10c3c0e08135f358ee6145620ee4cfbe23",
    APPRAISALS: "c19ba6216619c0c4d103b5dd7d99edb49f9722fba94a6eb9de824adfba1488d1",
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
        r"insulation|megger|clamp meter|rectifier|commutator|motor brushes|control gear|"
        r"generator controls?)\b",
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

# These are the only material core-experience contradictions identified by the
# bounded, person-by-person policy review. They are explicit reviewed source
# cases, not keyword triggers, scores, time windows or numerical thresholds.
MATERIAL_CORE_CONTRADICTIONS = {
    "K1200": {
        "record_ids": ["AP003496"],
        "finding": "Attributed motor-brush, commutator and optic-mechanism records conflict with AP003496's direct statement that the manager had not observed the plant work suggested by the record and that two requests for assistance were avoided.",
        "clarification": "Before a technical interview, establish which work Tomaltach performed personally, whether the optic and clockwork activities meet the employer's plant-maintenance criterion, and why AP003496 differs from the logs and other manager testimony.",
    },
}

# Reviewed questions that belong in a technical interview but do not dispute
# that the cited maintenance activity occurred. Keeping these separate from
# MATERIAL_CORE_CONTRADICTIONS prevents quality/supervision concerns from
# silently becoming pre-interview attribution gates.
REVIEWED_INTERVIEW_PROBES = {
    "K0478": {
        "record_ids": ["AP001159", "AP001160", "AP001161", "AP001162", "AP001165", "AP001167"],
        "finding": "The corroborated electrical records establish activity, while the appraisals retain mixed evidence about work quality, checking and consistency. Those concerns require concrete technical and safety questions, not denial of an interview.",
        "question": "At technical interview, ask Ossian to walk through CL010541 and CL010398: his personal responsibility, isolation and proving-dead steps, fault diagnosis, independent checks, and how the 2024 switchgear deficiency in AP001165 was addressed. Treat AP001167 as time-uncertain context and do not infer current HV authorisation.",
    },
}

# Appraisals are manager testimony, not observed competence. These deliberately
# narrow patterns surface selected role-related testimony; every keeper-code-
# keyed row is reviewed, while unmatched rows are explicitly labelled as not
# selected by this filter rather than characterized as irrelevant.
APPRAISAL_TOPIC_PATTERNS = {
    "electrical_or_controls": re.compile(
        r"\b(electrical|batter(?:y|ies)|standby banks?|boards?|distribution|switchgear|"
        r"switching|isolations?|11\s*kV|HV|high voltage|control side|generator controls?|"
        r"fault work|chasing faults|diagnostics|relay|plant)\b", re.I
    ),
    "mechanical_or_generating_plant": re.compile(
        r"\b(engines?|main sets?|generating plant|pumps?|pumped systems?|hydraulics?|"
        r"motors?|drives?|winch|derrick|haulage gear|lifting work)\b", re.I
    ),
    "height_or_access": re.compile(
        r"\b(height work|staging work|rope work|abseil inspections?|work on the gallery)\b", re.I
    ),
    "work_reporting": re.compile(r"\b(defect reporting|inspection reports?)\b", re.I),
    "adjacent_station_technical": re.compile(
        r"\b(optic|lamp and lens|light itself|fog signal|diaphone|VHF|AIS gear|"
        r"aton telemetry|radio work|lantern glass|ironwork)\b", re.I
    ),
}
APPRAISAL_CONCERN_PATTERNS = {
    "needs_supervision": re.compile(r"\bneeds supervision\b", re.I),
    "work_checked_behind": re.compile(r"\bhas to be checked behind\b", re.I),
    "below_expected_standard": re.compile(r"\bfalls below that expected\b", re.I),
    "recurring_shortfall": re.compile(r"\brecurring shortfall\b", re.I),
    "specific_deficiency": re.compile(r"\b(?:some )?deficiency has been noted\b", re.I),
    "weakness": re.compile(r"\bweak on\b", re.I),
    "identified_gap": re.compile(r"\bgap identified\b", re.I),
    "needs_work": re.compile(r"\bneeds work\b", re.I),
    "no_use_and_not_learning": re.compile(r"\bno use at all\b.*\bshows no sign of learning\b", re.I),
    "avoids_work": re.compile(r"\bwill not touch\b|\bfound reasons not to\b", re.I),
    "experience_disputed": re.compile(r"\bhas not, to my knowledge, carried out any of the plant work\b", re.I),
    "technical_improvement_objective": re.compile(r"\bimprovement objective relating to\b", re.I),
    "slow_or_difficult_start": re.compile(r"\bslow (?:with|start on)\b|\bthe difficulty this year has been\b", re.I),
    "directed_more_than_once": re.compile(r"\btold (?:him|her|them) twice about\b", re.I),
    "technical_not_strong_suit": re.compile(r"\bnot (?:his|her|their) strong suit\b", re.I),
    "authorisation_lapsed": re.compile(r"\bauthorisation for\b.*\blapsed\b.*\bnot been renewed\b", re.I),
    "remedial_input": re.compile(r"\breferred to district training for remedial input\b", re.I),
    "expressed_technical_concern": re.compile(r"\bI have a concern about\b", re.I),
    "still_developing": re.compile(r"\bstill finding (?:his|her|their) feet with\b", re.I),
}
APPRAISAL_SUPPORT_PATTERNS = {
    "go_to_person": re.compile(r"\bstation['’]s go-to\b", re.I),
    "made_proper_job": re.compile(r"\bmade a proper job of it\b", re.I),
    "resolved_failure": re.compile(r"\bwas the one who sorted it out\b", re.I),
    "trusted_by_manager": re.compile(r"\bhave come to rely on\b.*\bnever been let down\b", re.I),
    "explicit_capability": re.compile(r"\bgenuinely capable\b|\bcompetent\b", re.I),
    "good_standard": re.compile(r"\bto a good standard\b|\bproper standard\b", re.I),
    "sound": re.compile(r"\bis sound\b", re.I),
    "acceptable_for_grade": re.compile(r"\bconsidered acceptable for the grade\b", re.I),
    "performed_properly": re.compile(r"\b(?:was |were )?done properly\b|\bperformed properly\b", re.I),
    "satisfactory_standard": re.compile(r"\b(?:consistently |very )?satisfactory(?: standard| indeed)?\b", re.I),
    "adequate_working_knowledge": re.compile(r"\badequate working knowledge\b", re.I),
    "without_adverse_comment": re.compile(r"\bwithout adverse comment\b|\bno complaints\b", re.I),
    "positive_application": re.compile(r"\bapply themselves appropriately\b|\bgets it right\b|\bquietly gets on with\b", re.I),
    "technical_asset_or_strength": re.compile(r"\breal asset\b|\bremains a strength\b|\bstandard I have not seen bettered\b", re.I),
    "objective_achieved": re.compile(r"\bobjective relating to\b.*\bclosed as achieved\b", re.I),
    "peer_reference": re.compile(r"\bthe younger men go to\b|\bknows more about\b.*\bthan the engineers\b", re.I),
    "maintained_or_within_tolerance": re.compile(r"\battention to\b.*\bmaintained throughout\b|\bwithin tolerance\b", re.I),
    "positive_short_form": re.compile(r"\b(?:good on|well handled|gets on with|knows)\b|\bfine\b", re.I),
    "benchmark_standard": re.compile(r"\bat a standard the rest of us measure ourselves against\b", re.I),
}
APPRAISAL_CONTEXT_PATTERNS = {
    # Retain useful corroborating or contrary context without allowing these
    # phrases alone to change the decision gate.
    "careful_completion_testimony": re.compile(r"\bwill not leave\b.*\bhalf done\b", re.I),
    "technical_course_with_document_gap": re.compile(r"\battended the district course\b.*\bpaperwork never came back\b", re.I),
    "technical_objective": re.compile(r"\b(?:improvement|annual) objective relating to\b", re.I),
    "authorisation_status": re.compile(r"\bauthorisation for\b.*\b(?:lapsed|remains current)\b", re.I),
    "framework_or_evidence_reference": re.compile(r"\bcompetency framework reference\b|\b(?:supporting observation|principal evidence)(?:\s*:| relates to)", re.I),
    "ticket_administration": re.compile(r"\bno formal ticket\b.*\badministrative matter\b", re.I),
    "recorded_technical_observation": re.compile(r"\bthe thing I would put on record about\b", re.I),
}

# Two synthetic appraisal rows split a positive assessment from its technical
# object with a full stop ("Competent. the ... in particular."). These exact,
# hand-reviewed exceptions preserve that local relationship without weakening
# the same-sentence rule for unrelated praise or criticism elsewhere.
APPRAISAL_MANUAL_SELECTIONS = {
    "AP000490": {
        "excerpts": ["Competent.", "the distribution side in particular."],
        "topics": ["electrical_or_controls"],
        "support_signals": ["bounded_manual_competence_fragment"],
    },
    "AP000559": {
        "excerpts": ["Competent.", "the AIS gear in particular."],
        "topics": ["adjacent_station_technical"],
        "support_signals": ["bounded_manual_competence_fragment"],
    },
}

PRIMARY_APPRAISAL_TOPICS = {
    "electrical_or_controls",
    "mechanical_or_generating_plant",
    "height_or_access",
}
K1200_MATERIAL_LOG_IDS = ("CL005994", "CL007505", "CL009097", "CL009921")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def read_json(zf: zipfile.ZipFile, name: str):
    return json.loads(zf.read(name).decode("utf-8"))


def read_jsonl(zf: zipfile.ZipFile, name: str) -> list[dict]:
    return [json.loads(line) for line in zf.read(name).decode("utf-8").splitlines() if line.strip()]


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
    rows = []
    for line_number, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        row["_source_reference"] = f"{member.removeprefix(ROOT)}#L{line_number}"
        rows.append(row)
    return rows


def canonical_name(value: str | None) -> str | None:
    if not value:
        return None
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c.lower() for c in decomposed if c.isalnum() and not unicodedata.combining(c))


def numeric_identifier(value: str | None) -> str | None:
    """Normalize integer-like decimal/scientific IDs without inventing digits."""
    if not value:
        return None
    try:
        number = Decimal(value.strip().lstrip("'"))
    except InvalidOperation:
        return None
    if not number.is_finite() or number != number.to_integral_value():
        return None
    return str(int(number))


def identity_provenance(identifier_type: str, raw_value: str | None, keeper: dict) -> dict:
    if identifier_type == "keeper_code":
        expected = keeper["keeper_code"]
        normalized_raw = raw_value
        match = raw_value == expected
    elif identifier_type == "payroll_reference":
        expected = keeper.get("payroll_ref")
        normalized_raw = numeric_identifier(raw_value)
        normalized_expected = numeric_identifier(expected)
        match = normalized_raw is not None and normalized_raw == normalized_expected
    elif identifier_type == "name":
        expected = keeper.get("name")
        normalized_raw = canonical_name(raw_value)
        expected_names = {canonical_name(keeper.get("name")), canonical_name(keeper.get("name_ascii"))}
        match = normalized_raw is not None and normalized_raw in expected_names
    else:
        return {
            "identifier_type": "absent",
            "raw_value": None,
            "normalized_raw_value": None,
            "expected_value": None,
            "corroboration": "absent",
        }
    return {
        "identifier_type": identifier_type,
        "raw_value": raw_value,
        "normalized_raw_value": normalized_raw,
        "expected_value": expected,
        "normalized_expected_value": numeric_identifier(expected) if identifier_type == "payroll_reference" else canonical_name(expected) if identifier_type == "name" else expected,
        "corroboration": "corroborates" if match else "conflicts",
    }


def measurement_quality_flags(text: str) -> list[dict]:
    flags = []
    if re.search(r"\bmegger\b", text, re.I):
        match = re.search(r"\b\d+(?:\.\d+)?\s*(psi|bar|V|volts?)\b", text, re.I)
        if match:
            unit_kind = "pressure" if match.group(1).lower() in {"psi", "bar"} else "electrical-potential"
            flags.append(
                {
                    "code": "inconsistent_measurement_unit",
                    "observed": match.group(0),
                    "finding": f"The quoted Megger result uses a {unit_kind} unit rather than an insulation-resistance unit, so the activity is retained but the numerical measurement is unreliable.",
                }
            )
    if re.search(r"\bpump\b.*\bdelivery\b", text, re.I):
        match = re.search(r"\b\d+(?:\.\d+)?\s*(V|volts?)\b", text, re.I)
        if match:
            flags.append(
                {
                    "code": "inconsistent_measurement_unit",
                    "observed": match.group(0),
                    "finding": "The quoted pump delivery uses an electrical-potential unit, so the activity is retained but the numerical measurement is unreliable.",
                }
            )
    if re.search(r"\bAVR\b", text, re.I) and re.search(r"\bvolts?\s+set\b", text, re.I):
        match = re.search(r"\b\d+(?:\.\d+)?\s*ohms?\b", text, re.I)
        if match:
            flags.append(
                {
                    "code": "inconsistent_measurement_unit",
                    "observed": match.group(0),
                    "finding": "The quoted AVR voltage setting uses a resistance unit, so the activity is retained but the numerical measurement is unreliable.",
                }
            )
    return flags


def raw_corroboration(zf: zipfile.ZipFile, entry: dict, keeper: dict) -> dict:
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
        result.update(
            resolved=True,
            resolution="physical_line",
            raw_excerpt=lines[line_no - 1].strip(),
            identity_provenance=identity_provenance("absent", None, keeper),
            attribution_match=None,
        )
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
                    identity_provenance=identity_provenance("keeper_code", fields[3], keeper),
                )
                return result
        return result
    row_no = int(locator)
    lines = raw.decode("utf-8-sig", errors="replace").splitlines()
    if not (2 <= row_no <= len(lines)):
        return result
    header = [value.strip().lower() for value in next(csv.reader([lines[0]]))]
    row = next(csv.reader([lines[row_no - 1]]))
    values = dict(zip(header, row))
    if "keeper_id" in values:
        identity = identity_provenance("payroll_reference", values["keeper_id"], keeper)
    elif "keeper name" in values:
        identity = identity_provenance("name", values["keeper name"], keeper)
    else:
        identity = identity_provenance("absent", None, keeper)
    activity = values.get("description", values.get("activity", "")).lstrip("'")
    result.update(
        resolved=True,
        resolution="physical_csv_row_including_header",
        raw_keeper_name=values.get("keeper name"),
        raw_payroll_reference=values.get("keeper_id"),
        raw_activity=activity,
        attribution_match=True if identity["corroboration"] == "corroborates" else False if identity["corroboration"] == "conflicts" else None,
        identity_provenance=identity,
    )
    return result


def entry_categories(text: str) -> list[str]:
    return [name for name, pattern in CATEGORY_PATTERNS.items() if pattern.search(text)]


def normalized_work_template(text: str) -> str:
    normalized = text.lower()
    # The source uses "permit", "PTW" and "permit bk." for the same
    # permit-to-work document in otherwise identical isolation workflows.
    # Normalize the document label and its synthetic reference only in the
    # counting key; the original evidence text remains untouched.
    normalized = re.sub(
        r"\b(?:ptw(?:\s*/\s*\d+|\s+\d+)?|permit(?:\s+bk\.?\s*\d+\s+no\.?\s*\d+|\s+\d+)?)\b",
        " permit reference ",
        normalized,
        flags=re.I,
    )
    # Measurement values and their supplied units are one superficial slot.
    # This intentionally collapses malformed variants such as 3.6 bar,
    # 48 psi and 11.2 V without rewriting the quoted evidence itself.
    normalized = re.sub(
        r"\b\d+(?:\.\d+)?\s*(?:psi|bar|volts?|v|ohms?|amps?|a|hz|kw|rpm|°?c)\b",
        " measurement ",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(r"\d+(?:\.\d+)?", "#", normalized)
    normalized = re.sub(r"\bno\s*\.?\s*#", "no #", normalized)
    return re.sub(r"\W+", " ", normalized).strip()


def work_evidence_record(
    zf: zipfile.ZipFile,
    keeper: dict,
    personnel: dict,
    entry: dict,
    categories: list[str],
    score: int,
    evidence_role: str = "qualifying_work_example",
    interpretation_provenance: dict | None = None,
) -> dict:
    corroboration = raw_corroboration(zf, entry, keeper)
    if not corroboration["resolved"]:
        raise ValueError(f"unresolved source reference {entry['source_record']}")
    work_date = parse_date(entry["date"])
    personnel_join_date = parse_date(personnel.get("date_joined"))
    chronology = {
        "status": "work_not_before_precise_personnel_join_date",
        "work_date": entry["date"],
        "precise_personnel_join_date": personnel.get("date_joined"),
        "clean_profile_join_date": keeper.get("date_joined"),
        "personnel_source_reference": personnel["_source_reference"],
        "clean_source_reference": f"clean/keepers.json#{keeper['keeper_code']}/date_joined",
    }
    if personnel_join_date and work_date < personnel_join_date:
        chronology["status"] = "unresolved_work_predates_precise_personnel_join_date"
        chronology["finding"] = (
            f"The retained work is dated {entry['date']}, before the personnel export's precise joining date "
            f"{personnel['date_joined']}. Earlier service, differing date definitions or a source error are possible, "
            "but none is established. The work and both joining-date claims are retained."
        )
    return {
        "entry_id": entry["entry_id"],
        "date": entry["date"],
        "text": entry["text"],
        "station": entry["station"],
        "categories": categories,
        "clean_source": "clean/logbook_entries.json",
        "source_reference": entry["source_record"],
        "attribution": "clean_manual_attribution",
        "raw_corroboration": corroboration,
        "measurement_quality_flags": measurement_quality_flags(entry["text"]),
        "selection_score": score,
        "template_key": normalized_work_template(entry["text"]),
        "evidence_role": evidence_role,
        "interpretation_provenance": interpretation_provenance,
        "personnel_chronology": chronology,
    }


def select_work_evidence(
    zf: zipfile.ZipFile, keeper: dict, personnel: dict, entries: list[dict], as_of: date
) -> tuple[list[dict], dict]:
    """Review the complete clean history, then return a readable evidence sample."""
    candidates = []
    material_display_candidates = {}
    at_cutoff = [entry for entry in entries if parse_date(entry["date"]) <= as_of]
    for entry in entries:
        required_k1200 = keeper["keeper_code"] == "K1200" and entry["entry_id"] in K1200_MATERIAL_LOG_IDS
        if parse_date(entry["date"]) > as_of:
            continue
        categories = entry_categories(entry["text"])
        normally_qualifies = bool(ACTION_RE.search(entry["text"])) and bool(
            {"electrical", "mechanical"} & set(categories)
        )
        if normally_qualifies:
            score = 2 * len({"electrical", "mechanical", "fault_finding", "permit_or_isolation"} & set(categories))
            score += len(set(categories))
            candidate = (score, entry["date"], entry, categories)
            candidates.append(candidate)
            if required_k1200:
                material_display_candidates[entry["entry_id"]] = candidate
        elif required_k1200:
            # Retain this reviewed event because AP003496 disputes what the
            # broader history represents. It remains context-only: the text
            # does not silently gain a mechanical category and does not enter
            # the qualifying-pattern or recommendation evidence sets.
            material_display_candidates[entry["entry_id"]] = (
                0,
                entry["date"],
                entry,
                categories,
            )
    candidates.sort(key=lambda item: (item[0], item[1], item[2]["entry_id"]), reverse=True)
    distinct, normalized_seen = [], set()
    for score, _, entry, categories in candidates:
        # Collapse superficial asset-number and measurement variants so repeated
        # synthetic templates do not masquerade as diverse experience.
        normalized = normalized_work_template(entry["text"])
        if normalized in normalized_seen:
            continue
        distinct.append(work_evidence_record(zf, keeper, personnel, entry, categories, score))
        normalized_seen.add(normalized)

    # Five examples are normally sufficient for readability. K1200's four
    # named material entries are all retained because the appraisal directly
    # disputes what that log history represents.
    chosen = distinct[:5]
    if keeper["keeper_code"] == "K1200":
        required = []
        for entry_id in K1200_MATERIAL_LOG_IDS:
            if entry_id not in material_display_candidates:
                continue
            score, _, entry, categories = material_display_candidates[entry_id]
            normally_qualifies = any(item[2]["entry_id"] == entry_id for item in candidates)
            required.append(
                work_evidence_record(
                    zf,
                    keeper,
                    personnel,
                    entry,
                    categories,
                    score,
                    evidence_role="qualifying_work_example" if normally_qualifies else "material_context_only",
                    interpretation_provenance=None
                    if normally_qualifies
                    else {
                        "type": "reviewed_display_context",
                        "reason": "Retained because AP003496 directly disputes what K1200's plant-work history represents.",
                        "limit": "The record is not assigned a mechanical or electrical category, is not counted as a qualifying pattern and does not independently support the interview disposition.",
                    },
                )
            )
        chosen = required + [row for row in chosen if row["entry_id"] not in K1200_MATERIAL_LOG_IDS]
        chosen = chosen[: max(5, len(required))]

    # A reported category must always be inspectable through at least one
    # displayed source record. Add the strongest missing category example
    # without removing the readability sample or K1200's exceptions.
    category_support = {
        category: next(row for row in distinct if category in row["categories"])
        for category in sorted({category for row in distinct for category in row["categories"]})
    }
    chosen_ids = {row["entry_id"] for row in chosen}
    for row in category_support.values():
        if row["entry_id"] not in chosen_ids:
            chosen.append(row)
            chosen_ids.add(row["entry_id"])

    category_coverage = sorted({category for item in distinct for category in item["categories"]})
    dates = [entry["date"] for entry in at_cutoff]
    review = {
        "full_clean_history_reviewed": True,
        "source_entry_count": len(entries),
        "entries_at_or_before_cutoff": len(at_cutoff),
        "future_entries_not_used": len(entries) - len(at_cutoff),
        "history_date_range_at_cutoff": [min(dates), max(dates)] if dates else None,
        "qualifying_action_entry_count": len(candidates),
        "distinct_qualifying_examples": len(distinct),
        "canonical_pattern_keys": [row["template_key"] for row in distinct],
        "category_coverage": category_coverage,
        "displayed_entry_ids": [row["entry_id"] for row in chosen],
        "interpretation": "The complete clean log history was screened. Repeated numeric, measurement-value/unit, permit/PTW/permit-bk and superficial wording variants were collapsed only for a descriptive workflow count; display exceptions do not create pattern identities, and counts or repetition do not decide interview support or establish competence.",
    }
    return chosen, review


def build_appraisal_review(rows: list[dict], as_of: date) -> dict:
    """Process exact-code appraisals and select bounded technical testimony."""
    processed_ids, relevant, future_ids, future_relevant_ids, same_year_uncertain = [], [], [], [], []
    technical_topic_candidate_ids = []
    for row in sorted(rows, key=lambda item: (item["year"], item["record_id"])):
        processed_ids.append(row["record_id"])
        relevant_sentences, topic_set, concern_set, support_set, context_set = [], set(), set(), set(), set()
        has_technical_topic = False
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", row["text"]):
            sentence = sentence.strip()
            sentence_topics = {name for name, pattern in APPRAISAL_TOPIC_PATTERNS.items() if pattern.search(sentence)}
            has_technical_topic = has_technical_topic or bool(sentence_topics)
            sentence_concerns = {name for name, pattern in APPRAISAL_CONCERN_PATTERNS.items() if pattern.search(sentence)}
            sentence_supports = {name for name, pattern in APPRAISAL_SUPPORT_PATTERNS.items() if pattern.search(sentence)}
            sentence_context = {name for name, pattern in APPRAISAL_CONTEXT_PATTERNS.items() if pattern.search(sentence)}
            # Signals and topics must co-occur in the same sentence. This avoids,
            # for example, attaching a paint-work criticism to a separate engine
            # compliment elsewhere in the appraisal.
            if sentence_topics and (sentence_concerns or sentence_supports or sentence_context):
                relevant_sentences.append(sentence)
                topic_set.update(sentence_topics)
                concern_set.update(sentence_concerns)
                support_set.update(sentence_supports)
                context_set.update(sentence_context)
        manual = APPRAISAL_MANUAL_SELECTIONS.get(row["record_id"])
        if manual:
            for excerpt in manual["excerpts"]:
                if excerpt not in row["text"]:
                    raise ValueError(f"manual appraisal excerpt changed for {row['record_id']}")
                if excerpt not in relevant_sentences:
                    relevant_sentences.append(excerpt)
            topic_set.update(manual["topics"])
            support_set.update(manual["support_signals"])
            has_technical_topic = True
        if has_technical_topic:
            technical_topic_candidate_ids.append(row["record_id"])
        topics = sorted(topic_set)
        concerns = sorted(concern_set)
        supports = sorted(support_set)
        context = sorted(context_set)
        if row["year"] > as_of.year:
            future_ids.append(row["record_id"])
            temporal_use = "future_year_not_used"
        elif row["year"] == as_of.year:
            same_year_uncertain.append(row["record_id"])
            temporal_use = "same_year_timing_uncertain_context_only"
        else:
            temporal_use = "pre_cutoff_year"
        if topics and (concerns or supports or context):
            selected = {
                "record_id": row["record_id"],
                "year": row["year"],
                "date_precision": "year",
                "station_code": row["station"],
                "role_relevant_excerpt": relevant_sentences,
                "source_text_sha256": sha256(row["text"].encode("utf-8")),
                "source_reference": f"raw/appraisals/appraisals.jsonl#{row['record_id']}",
                "attribution": "exact_keeper_code",
                "topics": topics,
                "support_signals": supports,
                "concern_signals": concerns,
                "context_signals": context,
                "decision_time_treatment": temporal_use,
                "evidence_limit": "Manager testimony; useful for screening questions but not proof of competence, authorisation or the date of an event within the year.",
            }
            if temporal_use == "future_year_not_used":
                future_relevant_ids.append(row["record_id"])
            else:
                relevant.append(selected)
    pre_cutoff_adverse = [
        row
        for row in relevant
        if row["decision_time_treatment"] == "pre_cutoff_year"
        and row["concern_signals"]
    ]
    same_year_adverse = [
        row
        for row in relevant
        if row["decision_time_treatment"] == "same_year_timing_uncertain_context_only"
        and row["concern_signals"]
    ]
    strong_support = [
        row
        for row in relevant
        if row["decision_time_treatment"] == "pre_cutoff_year"
        and row["support_signals"]
        and PRIMARY_APPRAISAL_TOPICS.intersection(row["topics"])
    ]
    return {
        "attribution_rule": "Only rows carrying this profile's exact keeper_code were attached. Null-key and name-only rows were not guessed.",
        "processing_and_review_scope": "Every exact-code row was mechanically processed. The bounded manual review covered technical-topic candidates and named omissions used to refine the selector; this is not a claim of complete semantic human review of every appraisal sentence.",
        "keyed_rows_processed": len(rows),
        "processed_record_ids": processed_ids,
        "technical_topic_candidate_record_ids": technical_topic_candidate_ids,
        "role_relevant_testimony": relevant,
        "role_relevant_testimony_count": len(relevant),
        "future_year_record_ids_not_used": future_ids,
        "future_role_relevant_record_ids_not_used": future_relevant_ids,
        "same_year_record_ids_timing_uncertain": same_year_uncertain,
        "pre_cutoff_adverse_testimony_ids": [row["record_id"] for row in pre_cutoff_adverse],
        "same_year_adverse_testimony_ids": [row["record_id"] for row in same_year_adverse],
        "selected_adverse_testimony_ids": [
            row["record_id"] for row in relevant if row["concern_signals"]
        ],
        "strong_manager_support_ids": [row["record_id"] for row in strong_support],
        "context_only_record_ids": [
            row["record_id"] for row in relevant if row["context_signals"] and not row["support_signals"] and not row["concern_signals"]
        ],
        "decision_neutral_context_ids": [
            row["record_id"]
            for row in relevant
            if row["record_id"] not in {item["record_id"] for item in strong_support}
        ],
        "rows_not_selected_by_appraisal_filter": len(rows) - len(relevant) - len(future_relevant_ids),
        "unmatched_row_label": "not selected by the appraisal filter",
    }


STATION_NOTE_SELECTIONS = {
    "K0478": {
        "member": OSSIAN_NOTE,
        "line": 2,
        "exact_text": "Watched Ossian do isolations on the 11kV today. Textbook, except there is no textbook for it here.",
        "station_posting": "RAH:2016-2017",
        "personnel_name": "O RAGHNAILL O",
        "claim": "A 2017 Raheenvarra manager note says the manager watched Ossian perform 11 kV isolations and describes the work as textbook.",
        "limit": "Positive manager testimony only. It does not prove current or historical authorisation and does not establish that later switching or switchgear concerns were resolved.",
    },
    "K0847": {
        "member": AOIFE_NOTE,
        "line": 2,
        "exact_text": "Watched Aoife do chasing faults today. Textbook, except there is no textbook for it here.",
        "station_posting": "POR:2000-2004",
        "personnel_name": "NI MHURCHU A",
        "claim": "A 2003 Portnalee manager note says the manager watched Aoife chase faults and describes the work as textbook.",
        "limit": "Positive manager testimony only; it does not establish assessed competence, certification or current proficiency.",
    },
    "K0310": {
        "member": GEARALT_NOTE,
        "line": 2,
        "exact_text": "Gearalt is wasfe.d here. the boards is the best in the district and the stafioii does not need it.",
        "station_posting": "CNO:1993-1993",
        "personnel_name": "O HEIDHNEAIN G",
        "claim": "A 1993 Cnoclia note contains a damaged transcription naming Gearalt and saying the boards are the best in the district.",
        "limit": "The supplied transcription is visibly corrupted and the technical meaning is not silently repaired. It is a historical interview lead, not proof of current practice, and it does not create an exact-code-keyed appraisal in appraisals.jsonl.",
    },
}


def station_note_evidence(zf: zipfile.ZipFile, keeper: dict, personnel: dict) -> list[dict]:
    rule = STATION_NOTE_SELECTIONS.get(keeper["keeper_code"])
    if not rule:
        return []
    lines = zf.read(rule["member"]).decode("utf-8").splitlines()
    exact_text = lines[rule["line"] - 1]
    if exact_text != rule["exact_text"]:
        raise ValueError(f"station-note text changed for {keeper['keeper_code']}")
    if personnel["name"] != rule["personnel_name"] or rule["station_posting"] not in personnel["station_postings"]:
        raise ValueError(f"station-note personnel attribution failed for {keeper['keeper_code']}")
    source = f"{rule['member'].removeprefix(ROOT)}#L{rule['line']}"
    return [
        {
            "claim": rule["claim"],
            "exact_excerpt": exact_text,
            "source_reference": source,
            "source_text_sha256": sha256(zf.read(rule["member"])),
            "attribution": "bounded_name_station_year_corroboration",
            "attribution_basis": (
                f"The note body supplies the given name; the note's station/year context matches {rule['station_posting']} in "
                f"the personnel row {personnel['_source_reference']}, whose name is {personnel['name']}. The clean profile "
                f"supplies the expanded name {keeper['name']}. Attribution uses those combined facts and not the filename alone."
            ),
            "attribution_sources": [
                personnel["_source_reference"],
                f"clean/keepers.json#{keeper['keeper_code']}",
            ],
            "use": "interview_lead_only",
            "evidence_limit": rule["limit"],
        }
    ]


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


def add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def build_training(
    keeper: dict, learnhub_rows: list[dict], scheme_map: dict, as_of: date
) -> tuple[list[dict], list[dict], list[dict]]:
    claims, future, all_claims = [], [], []
    for row in sorted(learnhub_rows, key=lambda x: (x.get("completed_on") or "", x["id"])):
        module = row.get("scheme_module") or ""
        status = training_status(row, as_of)
        claim = {
            "record_id": row["id"],
            "module": module,
            "title": row["title"],
            "outcome": row["outcome"],
            "completed_on": row.get("completed_on"),
            "expires_on": row.get("expires_on"),
            "status_at_cutoff": status,
            "source_reference": f"raw/training/vendor-c-learnhub-2017-2026.json#{row['id']}",
        }
        scheme_code = module.split("-", 1)[0] if "-" in module else None
        scheme = scheme_map.get(scheme_code)
        completed = parse_date(row.get("completed_on"))
        supplied_expiry = parse_date(row.get("expires_on"))
        renewal_years = scheme.get("renewal_years") if scheme else None
        if row.get("outcome") == "Pass" and completed and supplied_expiry and renewal_years:
            nominal_expiry = add_years(completed, renewal_years)
            supplied_current = supplied_expiry >= as_of
            nominal_current = nominal_expiry >= as_of
            claim["expiry_comparison"] = {
                "supplied_expiry": supplied_expiry.isoformat(),
                "scheme_renewal_years": renewal_years,
                "nominal_scheme_rule_date": nominal_expiry.isoformat(),
                "dates_differ": supplied_expiry != nominal_expiry,
                "cutoff_status_disagrees": supplied_current != nominal_current and completed <= as_of,
                "supplied_status_at_cutoff": "current" if supplied_current else "expired",
                "nominal_rule_status_at_cutoff": "current" if nominal_current else "expired",
                "interpretation": "The nominal scheme-period calculation is a consistency check only. The supplied expiry and calculated date are preserved separately; issuer verification is required where they conflict and neither date is silently substituted for the other.",
            }
            if claim["expiry_comparison"]["cutoff_status_disagrees"]:
                claim["status_at_cutoff"] = "pass_expiry_conflict_at_cutoff"
        all_claims.append(claim)
        if claim["status_at_cutoff"] == "future_at_cutoff":
            future.append(claim)
        elif module.startswith(RELEVANT_TRAINING_PREFIXES):
            claims.append(claim)
    return claims, future, all_claims


def current_module(claims: list[dict], module: str) -> bool:
    return any(c["module"] == module and c["status_at_cutoff"] == "pass_current_at_cutoff" for c in claims)


def reconcile_clean_training_claims(keeper: dict, all_claims: list[dict], as_of: date) -> list[dict]:
    """Reconcile year-only clean completions to uniquely matching detailed Passes."""
    reconciliation = []
    for clean in keeper.get("training_records", []):
        if clean.get("outcome") != "completed":
            continue
        module = clean["module"]
        matches = [
            claim
            for claim in all_claims
            if claim["module"] == module
            and claim["outcome"] == "Pass"
            and claim.get("completed_on")
            and parse_date(claim["completed_on"]).year == clean["year"]
        ]
        source_reference = f"clean/keepers.json#{keeper['keeper_code']}/training_records/{module}/{clean['year']}"
        item = {
            "scheme": clean["scheme"],
            "module": module,
            "clean_claim": {"year": clean["year"], "outcome": clean["outcome"], "source_reference": source_reference},
            "matching_detailed_record_ids": [claim["record_id"] for claim in matches],
        }
        if len(matches) == 1:
            detailed = matches[0]
            item["matched_detailed_record"] = detailed
            if detailed["status_at_cutoff"] == "future_at_cutoff":
                item["temporal_status"] = "future_detailed_pass_not_established_at_cutoff"
                item["finding"] = (
                    f"The clean summary records a year-only {clean['year']} completion, but the uniquely corresponding "
                    f"detailed Pass {detailed['record_id']} was completed on {detailed['completed_on']}, after "
                    f"{as_of.isoformat()}. It remains future evidence and is not treated as established at the cutoff."
                )
            else:
                item["temporal_status"] = "established_by_matched_pre_cutoff_detailed_pass"
                item["finding"] = f"Detailed Pass {detailed['record_id']} establishes this completion by the cutoff."
        elif len(matches) > 1:
            item["temporal_status"] = "multiple_detailed_matches_timing_unresolved"
            item["finding"] = "Multiple same-year detailed Passes match the clean claim, so no single record is silently chosen."
        elif clean["year"] < as_of.year:
            item["temporal_status"] = "established_before_cutoff_by_clean_year_only_claim"
            item["finding"] = "The clean claim's year is wholly before the cutoff; no corresponding detailed Pass was identified."
        elif clean["year"] > as_of.year:
            item["temporal_status"] = "future_clean_year_only_claim_not_established"
            item["finding"] = "The clean claim's year is after the cutoff and is not treated as established."
        else:
            item["temporal_status"] = "same_year_clean_claim_timing_unknown"
            item["finding"] = (
                f"The clean claim supplies only {clean['year']}; without a reliable corresponding detailed date, its position "
                f"relative to {as_of.isoformat()} is unknown and it is not treated as established."
            )
        reconciliation.append(item)
    return reconciliation


def established_completed_modules(
    reconciliation: list[dict], all_claims: list[dict], scheme: str, as_of: date
) -> set[str]:
    established = {
        row["module"]
        for row in reconciliation
        if row["scheme"] == scheme
        and row["temporal_status"] in {
            "established_by_matched_pre_cutoff_detailed_pass",
            "established_before_cutoff_by_clean_year_only_claim",
        }
    }
    established.update(
        claim["module"]
        for claim in all_claims
        if claim["module"].startswith(scheme + "-")
        and claim["outcome"] == "Pass"
        and claim.get("completed_on")
        and parse_date(claim["completed_on"]) <= as_of
    )
    return established


def credential_conflicts(
    keeper: dict,
    claims: list[dict],
    all_claims: list[dict],
    clean_training_reconciliation: list[dict],
    clean_certification_summaries: list[dict],
    as_of: date,
) -> list[dict]:
    conflicts = []
    for claim in claims:
        comparison = claim.get("expiry_comparison")
        if comparison and comparison["cutoff_status_disagrees"]:
            conflicts.append(
                {
                    "code": "expiry_rule_conflict",
                    "scheme": claim["module"].split("-", 1)[0],
                    "record_id": claim["record_id"],
                    "claim": f"LearnHub supplies {comparison['supplied_expiry']} while the nominal {comparison['scheme_renewal_years']}-year scheme rule points to {comparison['nominal_scheme_rule_date']}.",
                    "finding": f"At {as_of.isoformat()}, the supplied expiry says {comparison['supplied_status_at_cutoff']} but the nominal scheme-rule date says {comparison['nominal_rule_status_at_cutoff']}; issuer verification is required before relying on either date.",
                    "source_references": [claim["source_reference"], f"employers/certification_schemes.json#{claim['module'].split('-', 1)[0]}"],
                }
            )
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
    for row in clean_training_reconciliation:
        if row["temporal_status"] in {
            "future_detailed_pass_not_established_at_cutoff",
            "future_clean_year_only_claim_not_established",
            "same_year_clean_claim_timing_unknown",
            "multiple_detailed_matches_timing_unresolved",
        }:
            refs = [row["clean_claim"]["source_reference"]]
            if row.get("matched_detailed_record"):
                refs.append(row["matched_detailed_record"]["source_reference"])
            conflicts.append(
                {
                    "code": "clean_training_temporal_reconciliation",
                    "scheme": row["scheme"],
                    "module": row["module"],
                    "claim": f"The clean training history records {row['module']} completed in {row['clean_claim']['year']}.",
                    "finding": row["finding"],
                    "source_references": refs,
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
    for summary in clean_certification_summaries:
        reconciliation = summary["source_summary_reconciliation"]
        if reconciliation["status"] == "unresolved_clean_summary_detailed_pass_disagreement":
            conflicts.append(
                {
                    "code": "clean_summary_detailed_module_disagreement",
                    "scheme": summary["scheme"],
                    "record_ids": reconciliation["expired_detailed_pass_record_ids"],
                    "claim": (
                        f"The clean {summary['scheme']} summary claims complete={summary['complete']}, "
                        f"valid_2026={summary['valid_2026']} and expires_year={summary['expires_year']}."
                    ),
                    "finding": reconciliation["finding"],
                    "source_references": [summary["source_reference"]]
                    + [row["source_reference"] for row in summary["detailed_module_reconciliation"] if row.get("record_id") in reconciliation["expired_detailed_pass_record_ids"]],
                }
            )
    completed_mecs = established_completed_modules(clean_training_reconciliation, all_claims, "MECS", as_of)
    highest = 0
    for stage in range(1, 6):
        if f"MECS-{stage}" in completed_mecs:
            highest = stage
        else:
            break
    later = sorted(m for m in completed_mecs if int(m.split("-")[1]) > highest)
    if later:
        if highest == 0:
            finding = (
                "The supplied records do not establish a consecutive Stage 1 award; later recorded modules do not fill "
                "that evidence gap. This describes the documented module sequence, not the person's actual awarded stage."
            )
        else:
            finding = (
                f"The supplied records establish a documented consecutive sequence through MECS-{highest}; later recorded "
                f"modules do not establish MECS-{highest + 1}. This does not determine the person's actual awarded stage."
            )
        conflicts.append(
            {
                "code": "consecutive_stage_not_established",
                "scheme": "MECS",
                "claim": f"Pre-cutoff supplied records establish completed modules {', '.join(sorted(completed_mecs))}.",
                "documented_consecutive_sequence_through": f"MECS-{highest}" if highest else None,
                "later_recorded_modules": later,
                "finding": finding,
                "source_references": [
                    f"clean/keepers.json#{keeper['keeper_code']}/training_records",
                    "raw/training/vendor-c-learnhub-2017-2026.json",
                    "employers/certification_schemes.json#MECS",
                ],
            }
        )
    return conflicts


def provisional_safety_mapping(claims: list[dict]) -> dict:
    return {
        "status": "provisional_mapping_not_employer_acceptance",
        "mapped_dated_passes": {
            need: {"module": module, "dated_pass_current": current_module(claims, module)}
            for need, module in ESSENTIAL_MODULES.items()
        },
        "unresolved_scope": "The O&M posting names sea survival, fire, first aid and working-at-height coverage but does not identify the accepted package. OSSC contains no height module; WAHS separately defines height safety, climbing and rescue. Employer/issuer confirmation is required.",
        "coverage_not_inferred": ["WAHS-2 ladder and tower climbing", "WAHS-4 tower rescue and casualty recovery"],
    }


def clean_summaries(keeper: dict, all_claims: list[dict], as_of: date) -> list[dict]:
    relevant = {"OSSC", "WAHS", "MECS", "MPMC", "HVAP", "SMOC", "LOSC"}
    summaries = []
    for c in keeper.get("certifications", []):
        if c.get("scheme") not in relevant:
            continue
        detailed = []
        for module in c.get("modules_held", []):
            passes = [
                claim
                for claim in all_claims
                if claim["module"] == module
                and claim["outcome"] == "Pass"
                and claim.get("completed_on")
                and parse_date(claim["completed_on"]) <= as_of
            ]
            latest = max(passes, key=lambda claim: (claim["completed_on"], claim["record_id"])) if passes else None
            if not latest:
                detailed.append(
                    {
                        "module": module,
                        "status": "no_matched_pre_cutoff_detailed_pass",
                        "finding": "No dated pre-cutoff detailed Pass was matched; this is missing evidence, not proof that no Pass exists.",
                    }
                )
                continue
            supplied_expiry = parse_date(latest.get("expires_on"))
            status = (
                "supplied_pass_expired_at_cutoff"
                if supplied_expiry and supplied_expiry < as_of
                else "supplied_pass_current_at_cutoff"
                if supplied_expiry
                else "supplied_pass_has_no_expiry"
            )
            detailed.append(
                {
                    "module": module,
                    "record_id": latest["record_id"],
                    "completed_on": latest["completed_on"],
                    "expires_on": latest.get("expires_on"),
                    "status": status,
                    "source_reference": latest["source_reference"],
                }
            )
        expired = [row for row in detailed if row["status"] == "supplied_pass_expired_at_cutoff"]
        if as_of.year == 2026 and c.get("valid_2026") and expired:
            source_reconciliation = {
                "status": "unresolved_clean_summary_detailed_pass_disagreement",
                "expired_detailed_pass_record_ids": [row["record_id"] for row in expired],
                "finding": (
                    f"The clean summary says this {c['scheme']} award is complete and valid in 2026 through "
                    f"{c.get('expires_year')}, while the latest supplied pre-cutoff detailed Pass for "
                    + ", ".join(f"{row['module']} ({row['record_id']}, expiry {row['expires_on']})" for row in expired)
                    + " is expired at the scenario cutoff. Both source claims are preserved. Renewal or replacement evidence outside the supplied detailed records remains possible, so issuer verification is required and the award is not declared invalid."
                ),
            }
        elif as_of.year != 2026:
            source_reconciliation = {
                "status": "clean_2026_validity_claim_not_compared_to_alternate_year",
                "expired_detailed_pass_record_ids": [],
                "finding": "The clean field is specifically a 2026 validity claim and is not reinterpreted as a claim about this alternate scenario year.",
            }
        else:
            source_reconciliation = {
                "status": "no_material_disagreement_identified_from_matched_detailed_passes",
                "expired_detailed_pass_record_ids": [],
                "finding": "No clean-validity versus latest matched detailed-Pass expiry disagreement was identified at the cutoff; missing detailed records remain missing evidence.",
            }
        summaries.append({
            "scheme": c["scheme"],
            "modules_held": c.get("modules_held", []),
            "modules_missing": c.get("modules_missing", []),
            "complete": c.get("complete"),
            "awarded_year": c.get("awarded_year"),
            "expires_year": c.get("expires_year"),
            "valid_2026": c.get("valid_2026"),
            "status": "clean_summary_claim_not_independent_verification",
            "source_reference": f"clean/keepers.json#{keeper['keeper_code']}/certifications/{c['scheme']}",
            "detailed_module_reconciliation": detailed,
            "source_summary_reconciliation": source_reconciliation,
        })
    return summaries


def individual_policy_review(
    keeper: dict,
    evidence: list[dict],
    work_review: dict,
    appraisal_review: dict,
    supplementary_evidence: list[dict],
    is_current: bool,
    as_of: date,
) -> tuple[str, str, dict, dict]:
    """Apply the approved qualitative policy after an explicit per-profile review."""
    categories = work_review["category_coverage"]
    core_evidence = [
        row for row in evidence if {"electrical", "mechanical"}.intersection(row["categories"])
    ]
    provenance_order = {"corroborates": 0, "absent": 1, "conflicts": 2}
    core_evidence = sorted(
        core_evidence,
        key=lambda row: (
            provenance_order[row["raw_corroboration"]["identity_provenance"]["corroboration"]],
            -int(row["date"].replace("-", "")),
            row["entry_id"],
        ),
    )
    selected = []
    for row in core_evidence:
        covered = {category for item in selected for category in item["categories"]}
        if not selected or {"electrical", "mechanical"}.intersection(row["categories"]) - covered:
            selected.append(row)
        if len(selected) == 2:
            break
    if not selected and core_evidence:
        selected.append(core_evidence[0])

    positive_ids = [
        row["record_id"]
        for row in appraisal_review["role_relevant_testimony"]
        if row["support_signals"]
    ]
    adverse_ids = appraisal_review["selected_adverse_testimony_ids"]
    same_year_ids = appraisal_review["same_year_record_ids_timing_uncertain"]
    raw_conflict_ids = [
        row["entry_id"]
        for row in evidence
        if row["raw_corroboration"]["identity_provenance"]["corroboration"] == "conflicts"
    ]
    available_appraisal_ids = {row["record_id"] for row in appraisal_review["role_relevant_testimony"]}
    material_rule = MATERIAL_CORE_CONTRADICTIONS.get(keeper["keeper_code"])
    material_ids = [record_id for record_id in material_rule["record_ids"] if record_id in available_appraisal_ids] if material_rule else []
    material = ({**material_rule, "record_ids": material_ids} if material_rule and material_ids else None)
    probe_rule = REVIEWED_INTERVIEW_PROBES.get(keeper["keeper_code"])
    probe_ids = [record_id for record_id in probe_rule["record_ids"] if record_id in available_appraisal_ids] if probe_rule else []
    reviewed_probe = ({**probe_rule, "record_ids": probe_ids} if probe_rule and probe_ids else None)
    if reviewed_probe and keeper["keeper_code"] == "K0478":
        preferred_probe_ids = ("CL010541", "CL010398", "CL010466")
        probe_work = [row for entry_id in preferred_probe_ids for row in evidence if row["entry_id"] == entry_id][:2]
        if not probe_work:
            probe_work = selected
        cited_work = ", ".join(row["entry_id"] for row in probe_work)
        question = (
            f"At technical interview, ask Ossian to walk through {cited_work}: his personal responsibility, isolation and proving-dead steps, "
            "fault diagnosis, independent checks, and how he verified the outcome."
        )
        if "AP001165" in probe_ids:
            question += " Ask how the 2024 switchgear deficiency in AP001165 was addressed."
        if "AP001167" in probe_ids:
            question += " Treat AP001167 as time-uncertain context and do not infer current HV authorisation."
        reviewed_probe["question"] = question
    supplementary_sources = [row["source_reference"] for row in supplementary_evidence]
    unresolved_questions = []
    if material:
        unresolved_questions.append(material["clarification"])
    elif reviewed_probe:
        unresolved_questions.append(reviewed_probe["question"])
    elif adverse_ids:
        unresolved_questions.append(
            f"Discuss the selected adverse testimony in {', '.join(adverse_ids)} alongside the cited work and any positive testimony; it is a question for the interview, not an automatic veto."
        )
    if raw_conflict_ids:
        unresolved_questions.append(
            f"The permitted clean/manual attribution for {', '.join(raw_conflict_ids)} is not corroborated by the cited raw identifier; preserve that provenance limitation and do not use those rows alone."
        )
    if not appraisal_review["processed_record_ids"] and is_current:
        unresolved_questions.append(
            "No exact keeper-code-keyed appraisal is supplied; this is an evidence gap, not a clean performance finding."
        )
    if same_year_ids:
        unresolved_questions.append(
            f"Appraisals {', '.join(same_year_ids)} have year-only {as_of.year} dates, so their position relative to {as_of.isoformat()} is unknown and they remain context only."
        )
    if keeper["keeper_code"] == "K0310":
        unresolved_questions.append(
            "The supplied work logs end in 2012; ask about subsequent and current practice without applying an invented recency threshold."
        )

    if not is_current:
        recommendation = "outside_current_redeployment_cohort"
        reason = "The clean profile and leavers export mark this person as having left; no current redeployment pathway is assessed."
        selection_action = "No current redeployment pathway is assessed for this leaver."
        summary_uncertainty = "Outside current cohort"
    elif not selected:
        recommendation = "insufficient_evidence"
        reason = (
            "The bounded sources do not contain a specific attributed work record establishing hands-on mechanical or electrical maintenance. "
            "This is missing evidence, not a finding that the person lacks experience."
        )
        selection_action = (
            "Before deciding on a technical interview, ask for a specific attributable example of hands-on mechanical or electrical plant maintenance, including equipment, personal responsibility and outcome."
        )
        summary_uncertainty = "Essential hands-on maintenance evidence not established"
    else:
        disciplines = sorted(
            {category for row in selected for category in row["categories"] if category in {"electrical", "mechanical"}}
        )
        examples = "; ".join(
            f"{row['entry_id']} ({row['date']}) records \"{row['text']}\""
            for row in selected
        )
        relevance = (
            f"This is specific, attributed evidence of hands-on {' and '.join(disciplines)} maintenance with transferable relevance to the O&M posting's plant-maintenance work."
        )
        if material:
            recommendation = "targeted_screening_first"
            supplementary_clause = (
                f" Positive station-note testimony in {', '.join(supplementary_sources)} is also retained, but it does not prove authorisation or silently resolve later concerns."
                if supplementary_sources else ""
            )
            reason = (
                f"{examples}. {relevance} However, material contradiction in {', '.join(material['record_ids'])}: {material['finding']}"
                f"{supplementary_clause} Clarification is needed before a technical interview; neither source is silently preferred."
            )
            selection_action = material["clarification"]
            summary_uncertainty = f"Material core contradiction: {', '.join(material['record_ids'])}"
        else:
            recommendation = "supported_technical_interview"
            appraisal_clause = ""
            if adverse_ids:
                appraisal_clause = (
                    f" Adverse testimony in {', '.join(adverse_ids)} is retained with positive testimony"
                    + (f" in {', '.join(positive_ids)}" if positive_ids else "")
                    + "; it supplies interview questions but does not erase the attributed activity or automatically bar an interview."
                )
            elif positive_ids:
                appraisal_clause = f" Positive testimony in {', '.join(positive_ids)} is an interview lead, not proof of competence."
            supplementary_clause = (
                f" Positive station-note testimony in {', '.join(supplementary_sources)} is retained as an interview lead, not proof of current or historical authorisation."
                if supplementary_sources else ""
            )
            reason = (
                f"{examples}. {relevance}{appraisal_clause}{supplementary_clause} A structured technical interview is supported; this is not a competence, eligibility, authorisation or mobilisation finding."
            )
            if reviewed_probe:
                reason += f" Reviewed interview focus ({', '.join(reviewed_probe['record_ids'])}): {reviewed_probe['finding']}"
                selection_action = reviewed_probe["question"]
                summary_uncertainty = f"Work-quality and checking questions retained for interview: {', '.join(reviewed_probe['record_ids'])}"
            else:
                selected_activity = " / ".join(f"{row['entry_id']}: {row['text']}" for row in selected)
                selection_action = (
                    f"Invite to a structured technical interview using {selected_activity}. Ask what the keeper personally did, the safe method used, how the fault or maintenance need was established, and how the outcome was verified."
                )
            if not reviewed_probe:
                if keeper["keeper_code"] == "K0310":
                    summary_uncertainty = "Historical evidence only; logs end 2012 and no keyed appraisal"
                elif same_year_ids:
                    summary_uncertainty = f"Year-only {as_of.year} appraisal timing is uncertain"
                elif adverse_ids:
                    summary_uncertainty = f"Adverse testimony retained for interview: {', '.join(adverse_ids)}"
                elif not appraisal_review["processed_record_ids"]:
                    summary_uncertainty = "No keyed appraisal; no clean-record inference"
                else:
                    summary_uncertainty = "Competence and mobilisation remain unestablished"

    criteria = {
        "reviewed_individually": True,
        "supporting_core_work_ids": [row["entry_id"] for row in selected],
        "descriptive_distinct_workflow_count": work_review["distinct_qualifying_examples"],
        "category_coverage": categories,
        "selected_positive_testimony_ids": positive_ids,
        "selected_adverse_testimony_ids": adverse_ids,
        "same_year_timing_uncertain_ids": same_year_ids,
        "material_core_contradiction_ids": material["record_ids"] if material else [],
        "reviewed_interview_probe_ids": reviewed_probe["record_ids"] if reviewed_probe else [],
        "ranking_used": False,
        "numerical_interview_threshold_used": False,
        "automatic_adverse_appraisal_gate_used": False,
        "policy": {
            "supported_technical_interview": "Specific attributed evidence supports plausible hands-on mechanical or electrical maintenance experience; adverse, sparse or old evidence is discussed but is not an automatic veto.",
            "targeted_screening_first": "A named material attribution problem or contradiction concerning the core experience claim must be clarified before a technical interview.",
            "insufficient_evidence": "The bounded sources do not establish essential hands-on mechanical or electrical maintenance; missing records are not proof that the person lacks experience.",
            "year_precision": f"A {as_of.year} year-only appraisal is context only because its position relative to {as_of.isoformat()} is unknown.",
        },
    }
    review = {
        "supporting_core_work_ids": criteria["supporting_core_work_ids"],
        "positive_testimony_ids": positive_ids,
        "positive_supplementary_sources": supplementary_sources,
        "adverse_testimony_ids": adverse_ids,
        "material_unresolved_issue": material["finding"] if material else None,
        "reviewed_interview_probe": reviewed_probe["finding"] if reviewed_probe else None,
        "unresolved_questions": unresolved_questions,
        "summary_uncertainty": summary_uncertainty,
        "selection_action": selection_action,
    }
    return recommendation, reason, criteria, review


def credential_action(claims: list[dict], module: str) -> str:
    records = [claim for claim in claims if claim["module"] == module]
    conflicts = [claim["record_id"] for claim in records if claim["status_at_cutoff"] == "pass_expiry_conflict_at_cutoff"]
    if conflicts:
        return f"{module}: ask the issuer to resolve the supplied-expiry/scheme-rule conflict in {', '.join(conflicts)} before deciding whether renewal is required."
    current = [claim["record_id"] for claim in records if claim["status_at_cutoff"] == "pass_current_at_cutoff"]
    if current:
        return f"{module}: present and issuer-verify the current dated Pass ({', '.join(current)})."
    expired = [claim["record_id"] for claim in records if claim["status_at_cutoff"] == "pass_expired"]
    if expired:
        return (
            f"{module}: the supplied Pass is expired ({', '.join(expired)}); ask the issuer which renewal, assessment or training route applies. "
            "The posting says the employer funds renewals, but it does not define the route or promise first-time training funding."
        )
    not_achieved = [claim["record_id"] for claim in records if claim["status_at_cutoff"] == "not_achieved"]
    if not_achieved:
        return f"{module}: Not achieved in {', '.join(not_achieved)} is not a Pass; complete training and assessment if progression is approved (first-time funding is not promised)."
    attended = [claim["record_id"] for claim in records if claim["status_at_cutoff"] == "attended_not_passed"]
    if attended:
        return f"{module}: Attended in {', '.join(attended)} is not a Pass; establish the required passed assessment if progression is approved (first-time funding is not promised)."
    return (
        f"{module}: no matched dated Pass is established; first verify any existing certificate with the issuer. "
        "Only if current required coverage remains unestablished should training and assessment be arranged "
        "if progression is approved (first-time funding is not promised)."
    )


def ordered_actions(
    keeper: dict,
    claims: list[dict],
    conflicts: list[dict],
    recommendation: str,
    policy_review: dict,
    is_current: bool,
) -> tuple[list[str], list[str]]:
    if not is_current:
        return ["No current redeployment pathway is assessed for this leaver."], []
    initial = [policy_review["selection_action"]]
    conflict_ids = sorted({c.get("record_id") for c in conflicts if c.get("record_id")})
    if conflict_ids:
        verification = f"First, ask the issuer to verify the conflicting expiry evidence for {', '.join(conflict_ids)} and retain both supplied and nominal dates until resolved."
    else:
        verification = "First, verify original certificates and resolve any listed source or prerequisite conflicts with the issuer."
    ossc_actions = " ".join(credential_action(claims, module) for module in ("OSSC-SS", "OSSC-FF", "OSSC-FA"))
    height_action = credential_action(claims, "WAHS-1")
    later = [
        "Only if the initial selection outcome supports progression, begin qualification and mobilisation checks; this ordering is not a statement that the person is already eligible.",
        verification,
        "Confirm directly that the person accepts repeated 80 m tower work, enclosed spaces, vessel transfer and the 14-on/14-off pattern before arranging courses.",
        "Obtain a current offshore medical fitness declaration before OSSC training or mobilisation.",
        f"After medical clearance, use the following as a provisional record check for sea survival, fire and first aid; confirm the employer's accepted offshore-safety package. {ossc_actions}",
        f"After OSSC-SS is issuer-verified current, use WAHS-1 only as a provisional height-safety mapping. Confirm whether the employer requires WAHS-2 climbing, WAHS-4 rescue, or other coverage before mobilisation. {height_action}",
        "Finally, as a recommended employer verification rather than an express O&M-posting requirement, consider permit, isolation and practical checks proportionate to the duties. The separate HV Authorised Person appointment has its own mandatory interview, certificate, experience and familiarisation rules.",
    ]
    return initial, later


def evaluate_keeper(zf, keeper, personnel, entries, appraisal_rows, learnhub_rows, scheme_map, as_of):
    evidence, work_review = select_work_evidence(zf, keeper, personnel, entries, as_of)
    appraisal_review = build_appraisal_review(appraisal_rows, as_of) if keeper["status"] == "current" else {
        "attribution_rule": "Leaver appraisals were not assessed because the person is outside the current cohort.",
        "processing_and_review_scope": "Leaver appraisals were not processed because the person is outside the current cohort.",
        "keyed_rows_processed": 0,
        "processed_record_ids": [],
        "technical_topic_candidate_record_ids": [],
        "role_relevant_testimony": [],
        "role_relevant_testimony_count": 0,
        "future_year_record_ids_not_used": [],
        "future_role_relevant_record_ids_not_used": [],
        "same_year_record_ids_timing_uncertain": [],
        "pre_cutoff_adverse_testimony_ids": [],
        "same_year_adverse_testimony_ids": [],
        "selected_adverse_testimony_ids": [],
        "strong_manager_support_ids": [],
        "context_only_record_ids": [],
        "decision_neutral_context_ids": [],
        "rows_not_selected_by_appraisal_filter": 0,
        "unmatched_row_label": "not selected by the appraisal filter",
    }
    claims, future, all_claims = build_training(keeper, learnhub_rows, scheme_map, as_of)
    clean_training_reconciliation = reconcile_clean_training_claims(keeper, all_claims, as_of)
    certification_summaries = clean_summaries(keeper, all_claims, as_of)
    conflicts = credential_conflicts(
        keeper,
        claims,
        all_claims,
        clean_training_reconciliation,
        certification_summaries,
        as_of,
    )
    coverage = provisional_safety_mapping(claims)
    categories = work_review["category_coverage"]
    category_evidence = []
    for category in categories:
        supporting = next(row for row in evidence if category in row["categories"])
        category_evidence.append(
            {
                "category": category,
                "entry_id": supporting["entry_id"],
                "date": supporting["date"],
                "text": supporting["text"],
                "source_reference": supporting["source_reference"],
            }
        )
    is_current = keeper["status"] == "current"
    supplementary = station_note_evidence(zf, keeper, personnel) if is_current else []

    recommendation, reason, recommendation_criteria, policy_review = individual_policy_review(
        keeper, evidence, work_review, appraisal_review, supplementary, is_current, as_of
    )
    eligibility = (
        "not_assessed_outside_current_cohort"
        if not is_current
        else "not_established_from_bounded_evidence"
        if recommendation == "insufficient_evidence"
        else "plausible_but_essential_evidence_incomplete"
    )
    initial_actions, later_actions = ordered_actions(
        keeper, claims, conflicts, recommendation, policy_review, is_current
    )
    actions = initial_actions + later_actions
    limitations = [
        {"code": "competence_not_inferred", "text": "Examples support interview potential only; tags, grades, hours and occurrence counts were not treated as proof of competence."},
    ]
    if is_current:
        limitations.append({"code": "medical_not_supplied", "text": "No current offshore medical evidence is present in the bounded sources."})
    if keeper["keeper_code"] == "K0310":
        if appraisal_review["processed_record_ids"]:
            raise ValueError("K0310 unexpectedly has a keyed appraisal")
        history_end = work_review["history_date_range_at_cutoff"][1]
        limitations.append(
            {
                "code": "historical_evidence_only",
                "text": f"Supplied clean logs end on {history_end} and no exact keeper-code-keyed appraisal is present. This is a historical-evidence limitation only; no recency threshold is applied and it does not automatically reject the person.",
            }
        )
    chronology_conflicts = []
    for item in evidence:
        chronology = item["personnel_chronology"]
        if chronology["status"] == "unresolved_work_predates_precise_personnel_join_date":
            chronology_conflicts.append(
                {
                    "code": "retained_work_predates_precise_personnel_join_date",
                    "entry_id": item["entry_id"],
                    "finding": chronology["finding"],
                    "source_references": [
                        item["source_reference"],
                        chronology["personnel_source_reference"],
                        chronology["clean_source_reference"],
                    ],
                }
            )
    if keeper["keeper_code"] == "K1538":
        switching_entry = next(e for e in entries if e["entry_id"] == "CL006360")
        switching_raw = raw_corroboration(zf, switching_entry, keeper)
        if not switching_raw["resolved"]:
            raise ValueError("unresolved Oileann hand-check citation CL006360")
        oileann_lines = zf.read(OILEANN_NOTE).decode("utf-8").splitlines()
        authorisation_excerpt = "She does the high voltage switching on this station and has done for years. She is the only person here I would let near it unsupervised. There is no ticket for it that anyone would recognise, because the internal authorisation was issued under an earlier surname at a station whose training records went in the 1997 changeover, and she has never once made a fuss about that."
        if oileann_lines[10] != authorisation_excerpt:
            raise ValueError("Oileann authorisation note text changed")
        supplementary.append(
            {
                "claim": "A 2011 manager note records generator-control fault-finding, years of station high-voltage switching and a claim that an internal authorisation under an unspecified earlier surname was lost with records in the 1997 changeover; clean entry CL006360 records work on an 11 kV board.",
                "exact_excerpt": authorisation_excerpt,
                "source_reference": "raw/appraisals/station_manager_notes/2011-nevisbeg-keeper-note.txt#L3,L7,L9,L11",
                "source_text_sha256": sha256(zf.read(OILEANN_NOTE)),
                "supporting_entry": {
                    "entry_id": switching_entry["entry_id"],
                    "date": switching_entry["date"],
                    "text": switching_entry["text"],
                    "source_reference": switching_entry["source_record"],
                    "attribution": "clean_manual_attribution",
                    "raw_corroboration": switching_raw,
                },
                "attribution_basis": f"The note names NI GHARBHAIL O/Oileann and the personnel row {personnel['_source_reference']} has one exact NI GHARBHAIL O match and a 2009-2017 Nevisbeg posting. The clean profile also places K1538 at Nevisbeg in 2011, but the note's tenure and authorisation chronology conflicts remain unresolved.",
                "attribution_sources": [personnel["_source_reference"], "clean/keepers.json#K1538"],
                "use": "interview_and_conditional_document_recovery_lead_only",
                "evidence_limit": "The note is testimony, not a current authorisation or proof of eligibility. If a separate AP route later becomes relevant, documentary recovery may be explored conditionally; no outcome is assumed.",
            }
        )
        chronology_conflicts.append(
            {
                "code": "oileann_station_tenure_conflict",
                "finding": f"The 2011 note says Oileann had been at Nevisbeg for eleven years (implying about 2000), while the personnel export records joining on {personnel['date_joined']} and a Nevisbeg posting beginning in 2009. The clean profile gives only 1998-01-01 as a year-level joining date. The testimony is retained as an interview lead, but its station-tenure chronology is not established.",
                "source_references": [
                    "raw/appraisals/station_manager_notes/2011-nevisbeg-keeper-note.txt#L2,L3,L7",
                    personnel["_source_reference"],
                    "clean/keepers.json#K1538/date_joined",
                    "clean/keepers.json#K1538/postings/NEV",
                ],
            }
        )
        chronology_conflicts.append(
            {
                "code": "oileann_authorisation_employment_chronology_question",
                "finding": f"The note claims an internal authorisation under an unspecified earlier surname was lost with station records in the 1997 changeover, while the personnel export records a joining date of {personnel['date_joined']}. If the claimed authorisation necessarily predates the changeover, it would appear to predate recorded employment; that is an inference requiring clarification, not an established contradiction or an invitation to invent an earlier surname.",
                "source_references": [
                    "raw/appraisals/station_manager_notes/2011-nevisbeg-keeper-note.txt#L11",
                    personnel["_source_reference"],
                ],
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
        "mobilisation_readiness": "not_established" if is_current else "not_assessed_outside_current_cohort",
        "recommendation_criteria": recommendation_criteria,
        "individual_policy_review": policy_review,
        "work_history_review": work_review,
        "relevant_experience": evidence,
        "appraisal_review": appraisal_review,
        "supplementary_evidence": supplementary,
        "identity_and_chronology_conflicts": chronology_conflicts,
        "experience_categories": categories,
        "experience_category_evidence": category_evidence,
        "credential_claims": claims,
        "clean_training_claim_reconciliation": clean_training_reconciliation,
        "clean_certification_summaries": certification_summaries,
        "credential_conflicts": conflicts,
        "future_evidence_not_used": future,
        "provisional_safety_coverage_mapping": coverage,
        "initial_selection_actions": initial_actions,
        "later_qualification_and_mobilisation_actions": later_actions,
        "remaining_requirements": later_actions,
        "next_actions": actions,
        "limitations": limitations,
    }


def markdown_report(payload: dict) -> str:
    summary = payload["summary"]
    current_rows = [row for row in payload["candidates"] if row["cohort_status"] == "current_redeployment_cohort"]
    lines = [
        "# Array O&M candidate recommendations",
        "",
        "> Synthetic Carrowmore data supplied for a Pearson job-application assessment. These are bounded development recommendations, not employment decisions.",
        "",
        f"Scenario date: **{payload['as_of']}**  ",
        f"Subset: **{summary['profiles']} profiles — {summary['current']} current keepers and {summary['leavers']} leavers outside the redeployment cohort**  ",
        f"Results: **{summary['supported_technical_interview']} supported technical interview, {summary['targeted_screening_first']} targeted screening first, {summary['insufficient_evidence']} insufficient evidence; {summary['outside_current_cohort']} outside the current cohort**",
        "",
        "Interview potential is deliberately separate from application eligibility and mobilisation readiness. No person is marked mobilisation-ready because medical fitness and direct acceptance of height/boat/enclosed-space conditions are not supplied.",
        "",
        "Requirement provenance: the O&M posting requires hands-on mechanical **or** electrical maintenance and named offshore-safety coverage. The separate HV Authorised Person posting is not an O&M interview gate. The OSSC/WAHS mapping is provisional pending employer/issuer confirmation, and permit/isolation/practical checks are recommendations unless expressly required for a separate appointment. Nominal fictional-scheme periods are consistency checks; no external GWO duration or policy is imported.",
        "",
        "## Current-keeper comparison",
        "",
        "| ID / name | Decision | Strongest evidence | Main uncertainty | Immediate next action |",
        "|---|---|---|---|---|",
    ]
    for row in sorted(current_rows, key=lambda item: item["keeper_code"]):
        evidence_ids = [item["entry_id"] for item in row["relevant_experience"][:2]]
        support_ids = row["appraisal_review"]["strong_manager_support_ids"][:1]
        strongest = ", ".join(evidence_ids + support_ids) or "No direct evidence"
        uncertainty = row["individual_policy_review"]["summary_uncertainty"]
        if row["interview_recommendation"] == "supported_technical_interview":
            immediate = "Structured technical interview"
        elif row["interview_recommendation"] == "targeted_screening_first":
            immediate = "Targeted evidence screen"
        else:
            immediate = "Obtain verifiable plant examples"
        name = (row["name_ascii"] or row["name"]).replace("|", "\\|")
        lines.append(f"| {row['keeper_code']} / {name} | `{row['interview_recommendation']}` | {strongest} | {uncertainty} | {immediate} |")
    lines.extend(["", "## Detailed evidence", ""])
    ordering = {"supported_technical_interview": 0, "targeted_screening_first": 1, "insufficient_evidence": 2, "outside_current_redeployment_cohort": 3}
    for row in sorted(payload["candidates"], key=lambda r: (ordering[r["interview_recommendation"]], r["keeper_code"])):
        appraisal_unmatched = row["appraisal_review"]["rows_not_selected_by_appraisal_filter"]
        appraisal_row_word = "row" if appraisal_unmatched == 1 else "rows"
        lines.extend([
            f"## {detailed_profile_heading(row)}",
            "",
            f"- Interview: `{row['interview_recommendation']}` — {row['recommendation_reason']}",
            f"- Application eligibility: `{row['application_eligibility']}`",
            f"- Mobilisation readiness: `{row['mobilisation_readiness']}`",
            f"- Core work records used for interview policy: {', '.join(row['individual_policy_review']['supporting_core_work_ids']) or 'none established'}",
            f"- Selected positive testimony: {', '.join(row['individual_policy_review']['positive_testimony_ids']) or 'none selected'}",
            f"- Selected adverse testimony: {', '.join(row['individual_policy_review']['adverse_testimony_ids']) or 'none selected'}",
            f"- Relevant evidence categories: {', '.join(row['experience_categories']) or 'none found'}",
            f"- Full clean log review: {row['work_history_review']['source_entry_count']} rows; {row['work_history_review']['distinct_qualifying_examples']} distinct relevant patterns after template collapse (descriptive only; not an interview threshold).",
            f"- Appraisal processing: {row['appraisal_review']['keyed_rows_processed']} exact keeper-code-keyed rows mechanically processed; {appraisal_unmatched} {appraisal_row_word} not selected by the appraisal filter. Bounded manual review covered technical-topic candidates and named omissions, not every sentence semantically.",
            "",
        ])
        if row["individual_policy_review"]["material_unresolved_issue"]:
            lines.append(f"- Material unresolved core issue: {row['individual_policy_review']['material_unresolved_issue']}")
            lines.append("")
        if row["individual_policy_review"]["unresolved_questions"]:
            lines.extend(["Unresolved questions retained for selection:", ""])
            for question in row["individual_policy_review"]["unresolved_questions"]:
                lines.append(f"- {question}")
            lines.append("")
        if row["experience_category_evidence"]:
            lines.extend(["Category support:", ""])
            for support in row["experience_category_evidence"]:
                lines.append(
                    f"- `{support['category']}` — {support['date']} — “{support['text']}” "
                    f"({support['entry_id']}; `{support['source_reference']}`)."
                )
            lines.append("")
        if row["relevant_experience"]:
            lines.append("Evidence:")
            lines.append("")
            for e in row["relevant_experience"]:
                raw = e["raw_corroboration"]
                identity = raw["identity_provenance"]
                if identity["corroboration"] == "corroborates" and identity["identifier_type"] == "payroll_reference":
                    attribution = f"clean/manual attribution corroborated by raw payroll value {identity['raw_value']} normalized to {identity['normalized_raw_value']}, matching clean payroll {identity['expected_value']}"
                elif identity["corroboration"] == "corroborates":
                    attribution = f"clean/manual attribution corroborated by raw {identity['identifier_type']} {identity['raw_value']}"
                elif identity["corroboration"] == "conflicts":
                    attribution = f"clean/manual attribution; raw {identity['identifier_type']} {identity['raw_value']} conflicts with clean {identity['expected_value']} and does not corroborate the person assignment"
                else:
                    attribution = "clean/manual attribution; the cited raw format has no person identifier, so identity is not independently corroborated"
                role_note = ""
                if e.get("evidence_role") == "material_context_only":
                    role_note = " Context only: retained for the named source contradiction; it is not assigned a mechanical/electrical category and does not independently support the disposition."
                lines.append(f"- {e['date']} — “{e['text']}” ({e['entry_id']}; `{e['source_reference']}`; {attribution}).{role_note}")
                chronology = e["personnel_chronology"]
                if chronology["status"] == "unresolved_work_predates_precise_personnel_join_date":
                    lines.append(f"  - Personnel chronology warning: {chronology['finding']} Personnel source: `{chronology['personnel_source_reference']}`; clean date source: `{chronology['clean_source_reference']}`.")
                for flag in e["measurement_quality_flags"]:
                    lines.append(f"  - Measurement warning `{flag['code']}`: {flag['finding']} Observed: `{flag['observed']}`.")
            lines.append("")
        selected_appraisals = row["appraisal_review"]["role_relevant_testimony"]
        if selected_appraisals:
            lines.extend(["Manager testimony selected as screening context:", ""])
            for item in selected_appraisals:
                signal = []
                if item["support_signals"]:
                    signal.append("support: " + ", ".join(item["support_signals"]))
                if item["concern_signals"]:
                    signal.append("concern: " + ", ".join(item["concern_signals"]))
                if item["context_signals"]:
                    signal.append("decision-neutral context: " + ", ".join(item["context_signals"]))
                excerpt = " / ".join(item["role_relevant_excerpt"])
                lines.append(f"- {item['year']} (year precision) — {excerpt} ({item['record_id']}; `{item['source_reference']}`; {'; '.join(signal)}). Manager testimony only, not competence or authorisation.")
            lines.append("")
        uncertain_appraisals = row["appraisal_review"]["same_year_record_ids_timing_uncertain"]
        if uncertain_appraisals:
            lines.append(f"- Same-year timing uncertainty: {', '.join(uncertain_appraisals)} are dated only to {payload['as_of'][:4]}, so they are context-only and do not establish a fact before {payload['as_of']}.")
            lines.append("")
        for e in row["supplementary_evidence"]:
            exact_excerpt = f" Exact excerpt: “{e['exact_excerpt']}”" if e.get("exact_excerpt") else ""
            lines.append(f"- Supplementary note: {e['claim']}{exact_excerpt} (`{e['source_reference']}`). {e['attribution_basis']} {e.get('evidence_limit', 'This is an interview lead, not an authorisation.')}")
            if e.get("supporting_entry"):
                s = e["supporting_entry"]
                lines.append(f"- Hand-check entry: {s['date']} — “{s['text']}” ({s['entry_id']}; `{s['source_reference']}`).")
            lines.append("")
        for conflict in row["identity_and_chronology_conflicts"]:
            lines.append(f"- Chronology conflict `{conflict['code']}`: {conflict['finding']}")
            lines.append("")
        if row["limitations"]:
            lines.extend(["Limitations:", ""])
            for limitation in row["limitations"]:
                lines.append(f"- `{limitation['code']}`: {limitation['text']}")
            lines.append("")
        if row["cohort_status"] == "leaver_outside_current_cohort":
            lines.extend(["No current credential, training or mobilisation pathway is assessed for this leaver.", ""])
            continue
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
            elif c["status_at_cutoff"] == "pass_expiry_conflict_at_cutoff":
                comparison = c["expiry_comparison"]
                lines.append(f"- Expiry conflict: {c['module']} Pass {c['record_id']} supplies {comparison['supplied_expiry']} ({comparison['supplied_status_at_cutoff']} at cutoff), while the nominal {comparison['scheme_renewal_years']}-year rule points to {comparison['nominal_scheme_rule_date']} ({comparison['nominal_rule_status_at_cutoff']}); issuer verification required (`{c['source_reference']}`).")
        for c in row["credential_conflicts"]:
            lines.append(f"- Conflict `{c['code']}`: {c['finding']}")
        if row["future_evidence_not_used"]:
            for future in row["future_evidence_not_used"]:
                lines.append(
                    f"- Future at cutoff and not used: {future['record_id']} — {future['module'] or future['title']}, "
                    f"{future['outcome']}, completed {future['completed_on']} (`{future['source_reference']}`)."
                )
        lines.extend(["", "Initial selection action:", ""])
        for action in row["initial_selection_actions"]:
            lines.append(f"- {action}")
        lines.extend(["", "Later qualification and mobilisation actions (only after selection progression):", ""])
        for action in row["later_qualification_and_mobilisation_actions"]:
            lines.append(f"- {action}")
        lines.append("")
    return "\n".join(lines) + "\n"


def compact_markdown(value: str, limit: int = 190) -> str:
    value = re.sub(r"\s+", " ", value).strip().replace("|", "\\|")
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def detailed_profile_heading(candidate: dict) -> str:
    return f"{candidate['keeper_code']} — {candidate['name_ascii'] or candidate['name']}"


def github_heading_anchor(heading: str) -> str:
    """Match GitHub's rendered-heading fragment rules for this ASCII-labelled report."""
    normalized = unicodedata.normalize("NFKC", heading.strip().lower())
    kept = []
    for character in normalized:
        if character.isalnum() or character in {"-", "_"} or character.isspace():
            kept.append(character)
    return "".join("-" if character.isspace() else character for character in kept)


def detailed_profile_anchor(candidate: dict) -> str:
    return github_heading_anchor(detailed_profile_heading(candidate))


def work_probe_focus(evidence: dict) -> tuple[str, str]:
    """Return a source-bounded interview focus without asserting competence."""
    text = evidence["text"].lower()
    categories = set(evidence["categories"])
    if "permit_or_isolation" in categories or re.search(r"\b(isolat|permit|ptw|earthed|proved dead)", text):
        return "electrical isolation", "explain the isolation boundary, proving-dead or earthing controls, and permit handback"
    if re.search(r"\b(avr|relay|contactor|control|battery|charger|switchgear|load[- ]shared?)\b", text):
        return "control systems", "explain the defect or setting basis, the change made, and the functional or load-sharing check"
    if "mechanical" in categories and re.search(r"\b(rebuilt|rebuild|overhaul|repaired|dressed|refitted|stripped|renewed)\b", text):
        return "mechanical overhaul", "explain the diagnosed defect, components worked on, and post-reassembly run checks"
    if "mechanical" in categories and re.search(r"\b(oil|filter|greas|belt|servic)\b", text):
        return "routine mechanical service", "explain the condition checks, work completed, and return-to-service checks"
    if re.search(r"\b(megger|continuity|tested?|checked?)\b", text):
        return "testing", "explain the test method, expected criterion, and how the recorded result was interpreted"
    if "fault_finding" in categories or re.search(r"\b(fault|traced?|diagnos|trip)\b", text):
        return "fault diagnosis", "explain the fault hypothesis, observations that isolated the cause, and the post-work check"
    if "electrical" in categories:
        return "electrical maintenance", "explain the safe isolation, work completed, and functional verification"
    return "mechanical maintenance", "explain the maintenance need, work completed, and functional verification"


def candidate_specific_probe(candidate: dict, core_rows: list[dict]) -> str:
    if candidate["keeper_code"] == "K0478":
        return (
            "CL010541 and CL010398 — fault diagnosis and electrical isolation: explain the isolation and proving-dead sequence, "
            "how the earth fault was located, the independent outcome checks, and how AP001165's switchgear deficiency was addressed. "
            "AP001167 is time-uncertain; do not infer current HV authorisation."
        )
    if candidate["keeper_code"] == "K1200":
        activities = " and ".join(
            f"{row['entry_id']} — {work_probe_focus(row)[0]}" for row in core_rows
        )
        return (
            f"{activities} — personal experience clarification: establish what Tomaltach performed personally, whether the optic and "
            "clockwork work meets the plant-maintenance criterion, and why AP003496 differs from the logs and other testimony."
        )

    grouped = {}
    for row in core_rows:
        label, question = work_probe_focus(row)
        grouped.setdefault((label, question), []).append(row["entry_id"])
    clauses = [
        f"{' and '.join(entry_ids)} — {label}: {question}"
        for (label, question), entry_ids in grouped.items()
    ]
    if candidate["keeper_code"] == "K0310":
        clauses.append("What later work demonstrates current practice, given that the supplied logs end in 2012?")
    return "; ".join(clauses) + "."


def evidence_quality_status(evidence: dict) -> str:
    identity = evidence["raw_corroboration"]["identity_provenance"]
    if identity["corroboration"] == "corroborates":
        parts = ["raw identity corroborated"]
    elif identity["corroboration"] == "conflicts":
        parts = [f"raw {identity['identifier_type']} conflicts with clean attribution — verify person"]
    else:
        parts = ["clean/manual attribution; raw identity absent — verify person"]
    for flag in evidence["measurement_quality_flags"]:
        parts.append(f"measurement anomaly `{flag['observed']}` — clarify value/unit")
    return f"{evidence['entry_id']}: " + "; ".join(parts)


def certification_disagreements(payload: dict) -> list[dict]:
    rows = []
    for candidate in payload["candidates"]:
        if candidate["cohort_status"] != "current_redeployment_cohort":
            continue
        for summary in candidate["clean_certification_summaries"]:
            reconciliation = summary["source_summary_reconciliation"]
            if reconciliation["status"] != "unresolved_clean_summary_detailed_pass_disagreement":
                continue
            rows.append(
                {
                    "keeper_code": candidate["keeper_code"],
                    "name": candidate["name_ascii"] or candidate["name"],
                    "scheme": summary["scheme"],
                    "clean_claim": (
                        f"complete={summary['complete']}, valid_2026={summary['valid_2026']}, "
                        f"expires_year={summary['expires_year']}"
                    ),
                    "clean_source_reference": summary["source_reference"],
                    "expired_record_ids": reconciliation["expired_detailed_pass_record_ids"],
                    "finding": reconciliation["finding"],
                }
            )
    return sorted(rows, key=lambda row: (row["keeper_code"], row["scheme"]))


def decision_brief(payload: dict) -> str:
    """Render the operator's short evidence-to-action view from canonical candidate data."""
    summary = payload["summary"]
    current = sorted(
        (row for row in payload["candidates"] if row["cohort_status"] == "current_redeployment_cohort"),
        key=lambda row: row["keeper_code"],
    )
    leavers = sorted(
        row["keeper_code"] for row in payload["candidates"] if row["cohort_status"] == "leaver_outside_current_cohort"
    )
    disagreements = certification_disagreements(payload)
    disagreement_people = sorted({row["keeper_code"] for row in disagreements})
    expired_record_count = sum(len(row["expired_record_ids"]) for row in disagreements)
    chronology_people = sorted(
        row["keeper_code"] for row in current if row["identity_and_chronology_conflicts"]
    )
    targeted = sorted(
        row["keeper_code"] for row in current if row["interview_recommendation"] == "targeted_screening_first"
    )
    targeted_count = summary["targeted_screening_first"]
    targeted_people_label = f"{targeted_count} {'person' if targeted_count == 1 else 'people'}"
    targeted_clarification_label = f"{targeted_count} targeted evidence {'clarification' if targeted_count == 1 else 'clarifications'}"

    lines = [
        "# Carrowmore Array O&M redeployment decision brief",
        "",
        "> Synthetic Pearson assessment data. This is an evidence-to-action prototype, not an employment decision, competence assessment or mobilisation approval.",
        "",
        f"Scenario date: **{payload['as_of']}**",
        "",
        "## A. Immediate answer and boundary",
        "",
        f"The permitted subset contains **{summary['profiles']} profiles: {summary['current']} current keepers and {summary['leavers']} leavers ({', '.join(leavers)}) outside the current redeployment cohort**. It is not a best-40 selection from all 340 personnel and is not representative of the full workforce.",
        "",
        f"The evidence supports **{summary['supported_technical_interview']} technical interviews**, **{targeted_clarification_label}** and **{summary['insufficient_evidence']} insufficient-evidence outcomes** among current keepers. These are next-step decisions, not hiring approvals. No person is declared competent, fully eligible, medically fit, authorised or mobilisation-ready.",
        "",
        "**Product decision contract:** For each of the 38 current keepers, show what experience is evidenced, what uncertainty materially affects progression, and the next justified step now; show training, medical and authorisation only as conditional later gates.",
        "",
        "The user is a redeployment officer assigning evidence-review work. Unlike a keyword search, this brief joins each activity to a person and exact source, retains contradictory testimony, respects the scenario cutoff and turns uncertainty into a named verification task.",
        "",
        "## B. Cohort action summary",
        "",
        "These work items are orthogonal; a person may appear in more than one. They are not score buckets or a ranking.",
        "",
        "| Work item | Current people / records | Operator action |",
        "|---|---:|---|",
        f"| Interview with person-specific verification | {summary['supported_technical_interview']} people | Use the exact work records and probe in the queue below; test personal responsibility, safe method and verified outcome. |",
        f"| Targeted core-experience clarification | {targeted_people_label} ({', '.join(targeted) or 'none'}) | Resolve the cited occurrence/attribution contradiction before technical interview. |",
        f"| Identity or chronology reconciliation | {len(chronology_people)} people ({', '.join(chronology_people) or 'none'}) | Preserve both claims and resolve the cited source/date discrepancy; do not delete the work record. |",
        f"| Clean-summary versus detailed-Pass reconciliation | {len(disagreement_people)} people; {len(disagreements)} summaries; {expired_record_count} expired detailed records | Send the paired claims and record IDs to the issuer; do not declare the award invalid or prescribe training from the mismatch alone. |",
        f"| Later conditional safety, medical and permission gates | {len(current)} people | Only after selection progression: verify certificates and willingness, then medical prerequisites, safety coverage and employer checks. |",
        "",
        "## C. Actionable queue for all 38 current people",
        "",
        "Stable by keeper code; no ranking is implied. Detailed quotations, provenance and later conditional actions remain in [recommendations.md](recommendations.md).",
        "",
        "| Keeper | Substantiated transferable activity | Disposition | Specific probe / clarification | Evidence quality | Other verification | Next action now |",
        "|---|---|---|---|---|---|---|",
    ]

    for candidate in current:
        evidence_by_id = {row["entry_id"]: row for row in candidate["relevant_experience"]}
        core_ids = candidate["individual_policy_review"]["supporting_core_work_ids"]
        core_rows = [evidence_by_id[entry_id] for entry_id in core_ids if entry_id in evidence_by_id]
        activity = "; ".join(
            f"{row['entry_id']}: {compact_markdown(row['text'], 92)}" for row in core_rows[:2]
        ) or "No essential hands-on example established"
        probe = candidate_specific_probe(candidate, core_rows) if core_rows else candidate["initial_selection_actions"][0]
        cited_rows = list(core_rows)
        cited_ids = {row["entry_id"] for row in cited_rows}
        for entry_id in re.findall(r"CL\d{6}", probe):
            if entry_id in evidence_by_id and entry_id not in cited_ids:
                cited_rows.append(evidence_by_id[entry_id])
                cited_ids.add(entry_id)
        evidence_quality = "<br>".join(evidence_quality_status(row) for row in cited_rows)

        verification = []
        if candidate["identity_and_chronology_conflicts"]:
            verification.append(
                "source/chronology: " + ", ".join(row["code"] for row in candidate["identity_and_chronology_conflicts"])
            )
        candidate_disagreements = [row for row in disagreements if row["keeper_code"] == candidate["keeper_code"]]
        if candidate_disagreements:
            verification.append(
                "issuer: " + ", ".join(
                    f"{row['scheme']} ({'/'.join(row['expired_record_ids'])})" for row in candidate_disagreements
                )
            )
        future_ids = [row["record_id"] for row in candidate["future_evidence_not_used"]]
        if future_ids:
            verification.append("future-at-cutoff evidence not usable: " + ", ".join(future_ids))
        if not verification:
            verification.append("personal responsibility and outcome; credentials, medical fitness and work-condition acceptance remain unestablished")

        if candidate["interview_recommendation"] == "supported_technical_interview":
            next_action = "Run the cited technical interview"
        elif candidate["interview_recommendation"] == "targeted_screening_first":
            next_action = "Resolve the cited core-experience contradiction"
        else:
            next_action = "Request one specific attributable plant-maintenance example"
        anchor = detailed_profile_anchor(candidate)
        keeper = f"[{candidate['keeper_code']} / {candidate['name_ascii'] or candidate['name']}](recommendations.md#{anchor})"
        lines.append(
            f"| {keeper} | {compact_markdown(activity)} | `{candidate['interview_recommendation']}` | "
            f"{compact_markdown(probe, 360)} | {evidence_quality} | "
            f"{compact_markdown('; '.join(verification), 220)} | {next_action} |"
        )

    by_code = {row["keeper_code"]: row for row in current}
    k0478 = by_code["K0478"]
    k1200 = by_code["K1200"]
    certification_case = next((row for row in disagreements if row["keeper_code"] == "K0354"), disagreements[0] if disagreements else None)
    k0592_future = next(row for row in by_code["K0592"]["future_evidence_not_used"] if row["record_id"] == "LH500977")
    k0478_core = ", ".join(k0478["individual_policy_review"]["supporting_core_work_ids"])
    k0478_probe_ids = ", ".join(k0478["recommendation_criteria"]["reviewed_interview_probe_ids"])
    k1200_qualifying = [row["entry_id"] for row in k1200["relevant_experience"] if row["evidence_role"] == "qualifying_work_example"]
    k1200_context = [row["entry_id"] for row in k1200["relevant_experience"] if row["evidence_role"] == "material_context_only"]
    k1200_material_ids = k1200["recommendation_criteria"]["material_core_contradiction_ids"]
    if k1200_material_ids:
        k1200_case_title = "### K1200 — direct dispute about personal plant experience"
        k1200_case_finding = f"{', '.join(k1200_material_ids)} directly disputes the plant work suggested by the records."
    else:
        k1200_case_title = "### K1200 — experience evidence available without a cutoff-date contradiction"
        k1200_case_finding = "No named material core-experience contradiction is available at this scenario cutoff."
    lines.extend(
        [
            "",
            "## D. Selected cases showing different operator actions",
            "",
            "### K0478 — experience established; quality and safety tested in interview",
            "",
            f"Corroborated electrical work {k0478_core} supports interview. Reviewed appraisal evidence {k0478_probe_ids} retains the quality/checking evidence available at this cutoff, and the 2017 Raheenvarra note is positive testimony rather than authorisation. **Action:** {k0478['initial_selection_actions'][0]}",
            "",
            k1200_case_title,
            "",
            f"Qualifying records available at the cutoff are {', '.join(k1200_qualifying)}. Context-only records are {', '.join(k1200_context) or 'none'} and gain no silent mechanical or electrical category. {k1200_case_finding} **Action:** {k1200['initial_selection_actions'][0]}",
            "",
            "### K0592 — future evidence cannot cross the scenario cutoff",
            "",
            f"{k0592_future['record_id']} records a {k0592_future['module']} Pass completed {k0592_future['completed_on']}, after {payload['as_of']} ({k0592_future['source_reference']}). **Action:** keep it visible as future evidence but do not use it to establish the person's position at the scenario date.",
            "",
            "## E. Systemic evidence-reconciliation opportunity",
            "",
            f"Independent derivation from the generated candidate records finds **{len(disagreements)} conflicting clean certification summaries, {expired_record_count} expired detailed Pass records and {len(disagreement_people)} affected current people**: {', '.join(disagreement_people)}. K1200 accounts for {sum(row['keeper_code'] == 'K1200' for row in disagreements)} summary disagreements and {sum(len(row['expired_record_ids']) for row in disagreements if row['keeper_code'] == 'K1200')} expired records. This concentration is reported, not generalized to the full workforce.",
            "",
            "| Keeper / scheme | Clean summary claim | Expired detailed Pass IDs | Neutral next action |",
            "|---|---|---|---|",
        ]
    )
    if certification_case:
        lines[lines.index("### K0592 — future evidence cannot cross the scenario cutoff"):lines.index("### K0592 — future evidence cannot cross the scenario cutoff")] = [
            f"### {certification_case['keeper_code']} — clean certification claim needs issuer reconciliation",
            "",
            f"The clean {certification_case['scheme']} summary ({certification_case['clean_source_reference']}) says {certification_case['clean_claim']}, while detailed Pass {', '.join(certification_case['expired_record_ids'])} is expired at the cutoff. **Action:** give both claims to the issuer; renewal outside the supplied detail remains possible, so do not declare the award invalid or prescribe training yet.",
            "",
        ]
    for row in disagreements:
        lines.append(
            f"| {row['keeper_code']} / {row['scheme']} | {row['clean_claim']} (`{row['clean_source_reference']}`) | "
            f"{', '.join(row['expired_record_ids'])} | Ask the issuer for current documentary evidence; retain both claims until resolved. |"
        )
    lines.extend(
        [
            "",
            "## F. Conditional progression and limitations",
            "",
            "1. Complete the interview or targeted evidence clarification first.",
            "2. If progression remains supported, verify original certificates and reconcile competing source claims with the issuer before spending on training.",
            "3. Confirm willingness for tower work, enclosed spaces, vessel transfer and the 14-on/14-off pattern.",
            "4. Establish medical fitness before OSSC training or mobilisation, then confirm the employer-accepted offshore-safety, climbing and rescue package and its prerequisites.",
            "5. Treat permit, isolation and practical checks as recommended employer verification unless an express requirement applies. The separate HV Authorised Person appointment is not imported as an O&M interview gate.",
            "",
            "Training duration, price, availability, current medical fitness, willingness, competence and authorisation remain unknown or unestablished unless an exact source says otherwise. Nominal fictional-scheme expiry calculations are consistency checks, not substituted authoritative dates.",
            "",
            "The original Pearson brief DOCX is not present in this workspace. This artifact follows the verified requirements recorded for the assessment and does not claim the brief was reread during this correction.",
        ]
    )
    return "\n".join(lines) + "\n"


def build(zip_path: Path, as_of: date) -> dict:
    with zipfile.ZipFile(zip_path) as zf:
        fingerprints = verify_inputs(zip_path, zf)
        keepers = read_json(zf, KEEPERS)
        logs = read_json(zf, LOGS)
        appraisals = read_jsonl(zf, APPRAISALS)
        learnhub = read_json(zf, LEARNHUB)["records"]
        schemes = read_json(zf, SCHEMES)["schemes"]
        scheme_map = {scheme["code"]: scheme for scheme in schemes}
        current_people = parse_personnel(zf, CURRENT)
        leavers = parse_personnel(zf, LEAVERS)
        if len(keepers) != 40 or Counter(k["status"] for k in keepers) != {"current": 38, "left": 2}:
            raise ValueError("clean subset is not the expected 38 current / 2 left")
        current_ids = {r["keeper_code"] for r in current_people}
        leaver_ids = {r["keeper_code"] for r in leavers}
        personnel_by_id = {row["keeper_code"]: row for row in current_people + leavers}
        for k in keepers:
            expected = current_ids if k["status"] == "current" else leaver_ids
            if k["keeper_code"] not in expected:
                raise ValueError(f"personnel cohort conflict for {k['keeper_code']}")
        by_keeper_logs = defaultdict(list)
        by_keeper_appraisals = defaultdict(list)
        by_keeper_training = defaultdict(list)
        for row in logs:
            by_keeper_logs[row["keeper_code"]].append(row)
        for row in learnhub:
            by_keeper_training[row["keeper_code"]].append(row)
        # Exact keeper codes are the only permitted appraisal join. The 1,728
        # null-key rows are deliberately left unattached; names are not guessed.
        for row in appraisals:
            if row.get("keeper_code"):
                by_keeper_appraisals[row["keeper_code"]].append(row)
        candidates = [
            evaluate_keeper(
                zf,
                k,
                personnel_by_id[k["keeper_code"]],
                by_keeper_logs[k["keeper_code"]],
                by_keeper_appraisals[k["keeper_code"]],
                by_keeper_training[k["keeper_code"]],
                scheme_map,
                as_of,
            )
            for k in sorted(keepers, key=lambda x: x["keeper_code"])
        ]
    counts = Counter(c["interview_recommendation"] for c in candidates)
    summary_disagreements = [
        summary
        for candidate in candidates
        if candidate["cohort_status"] == "current_redeployment_cohort"
        for summary in candidate["clean_certification_summaries"]
        if summary["source_summary_reconciliation"]["status"] == "unresolved_clean_summary_detailed_pass_disagreement"
    ]
    disagreement_people = {
        candidate["keeper_code"]
        for candidate in candidates
        if candidate["cohort_status"] == "current_redeployment_cohort"
        if any(
            summary["source_summary_reconciliation"]["status"] == "unresolved_clean_summary_detailed_pass_disagreement"
            for summary in candidate["clean_certification_summaries"]
        )
    }
    return {
        "schema_version": 6,
        "dataset": "synthetic Carrowmore Pearson assessment pack",
        "as_of": as_of.isoformat(),
        "scope": "Permitted 40-profile clean subset; 38 current keepers assessed and two leavers explicitly retained outside the current cohort.",
        "decision_boundary": "Evidence-led interview triage only; not a competence, eligibility or mobilisation determination.",
        "source_fingerprints": fingerprints,
        "employer_requirement_source": "employers/carrowmore-array-om-technician.md",
        "certification_definition_source": "employers/certification_schemes.json",
        "certification_schemes_loaded": [s["code"] for s in schemes],
        "requirement_provenance": {
            "pearson_brief": {
                "classification": "Pearson assessment requirement",
                "local_status": "not present in the current workspace; hash and sections 3-7 findings are recorded in CARROWMORE_RULES_AUDIT_20261011.md and SOURCE_FINGERPRINTS.json",
                "recorded_sha256": "93dea408967cc43fb273a09ff613a801f195f126a51bfa80a9991687914626d2",
            },
            "om_role": {
                "classification": "synthetic scenario requirement",
                "source": "employers/carrowmore-array-om-technician.md",
                "experience": "Hands-on mechanical or electrical maintenance experience on plant the person was responsible for.",
            },
            "hv_authorised_person": {
                "classification": "separate synthetic appointment, not an O&M interview requirement",
                "source": "employers/carrowmore-array-hv-authorised-person.md",
                "scope": "The AP posting separately requires HVAP, full OSSC, medical fitness, documented switching experience, an AP interview and site familiarisation.",
                "insurer_scope_ambiguity": "The HVAP scheme note says insurer-mandated for the Carrowmore Array, while the mandatory insurer language is explicit in the separate AP posting. The exact boundary for individual O&M duties is not supplied; no AP requirement is imported wholesale into O&M triage.",
            },
            "safety_mapping": {
                "classification": "provisional implementation mapping",
                "scope": "OSSC-SS/FF/FA and WAHS-1 are record checks, not proof of an employer-accepted package. The posting does not specify whether WAHS-2 climbing, WAHS-4 rescue or another package is required.",
            },
            "employer_checks": {
                "classification": "recommended verification, not an express O&M-posting requirement",
                "scope": "Permit, isolation and practical checks are proposed in proportion to duties. The O&M posting states assessed capability at offer but does not prescribe that exact suite.",
            },
            "scheme_periods": {
                "classification": "fictional supplied definitions",
                "scope": "Supplied renewal periods and prerequisites are preserved. Nominal dates are consistency checks requiring issuer verification where inconsistent; no GWO duration or external policy is imported as binding.",
            },
        },
        "summary": {
            "profiles": len(candidates),
            "current": sum(c["cohort_status"] == "current_redeployment_cohort" for c in candidates),
            "leavers": sum(c["cohort_status"] == "leaver_outside_current_cohort" for c in candidates),
            "supported_technical_interview": counts["supported_technical_interview"],
            "targeted_screening_first": counts["targeted_screening_first"],
            "insufficient_evidence": counts["insufficient_evidence"],
            "outside_current_cohort": counts["outside_current_redeployment_cohort"],
            "appraisal_source_rows": len(appraisals),
            "appraisal_rows_with_keeper_code": sum(bool(row.get("keeper_code")) for row in appraisals),
            "appraisal_rows_without_keeper_code_unattached": sum(not row.get("keeper_code") for row in appraisals),
            "appraisal_rows_processed_for_current_cohort": sum(c["appraisal_review"]["keyed_rows_processed"] for c in candidates),
            "appraisal_technical_topic_candidate_rows": sum(len(c["appraisal_review"]["technical_topic_candidate_record_ids"]) for c in candidates),
            "appraisal_rows_selected_for_role_relevant_testimony": sum(c["appraisal_review"]["role_relevant_testimony_count"] for c in candidates),
            "clean_summary_detailed_pass_disagreement_summaries": len(summary_disagreements),
            "clean_summary_detailed_pass_expired_records": sum(
                len(summary["source_summary_reconciliation"]["expired_detailed_pass_record_ids"])
                for summary in summary_disagreements
            ),
            "current_people_with_clean_summary_disagreement": len(disagreement_people),
        },
        "method": {
            "work_evidence": "Every clean log entry for each profile is reviewed. An entry normally needs an explicit maintenance action plus an electrical or mechanical plant term; superficial numeric, measurement and equivalent permit/PTW/permit-bk workflow variants are collapsed only for diversity counting. The strongest examples and at least one exact cited record for every claimed category are shown, except named material records needed to explain a conflict. Counts, hours and repetition are not competence.",
            "appraisals": "Every appraisal carrying an exact current-cohort keeper_code is mechanically processed. A bounded manual review covered technical-topic candidates and named omissions used to refine the same-sentence selector; this is not a claim of complete semantic human review of all 305 rows. Name-only/null-key rows are not attached. Year-only records matching the scenario year are context-only; future years are excluded from testimony and conclusions.",
            "decision_categories": "supported_technical_interview; targeted_screening_first; insufficient_evidence; outside_current_redeployment_cohort. Every current profile is reviewed individually; no score, rank, numerical workflow threshold, adverse-appraisal window or keyword veto decides the category.",
            "supported_technical_interview": "Specific attributed evidence supports plausible hands-on mechanical or electrical maintenance. The reason explains the activity and transferable relevance; adverse, sparse or old evidence alone is not a veto.",
            "targeted_screening_first": "A named material unresolved attribution problem or contradiction concerning the core experience claim requires clarification before a technical interview.",
            "insufficient_evidence": "The bounded sources do not establish essential hands-on mechanical or electrical maintenance. Missing evidence is not a finding that the person lacks experience.",
            "training": "Dated LearnHub outcome and supplied expiry are evaluated at the explicit cutoff. Pass, Attended and Not achieved remain distinct. Year-only clean completions are reconciled to reliable detailed dates before derived module sequences are stated. Clean validity summaries and detailed module expiries remain separate source claims. Nominal fictional-scheme dates are consistency checks only; issuer verification is required where sources disagree.",
            "height_mapping": "OSSC-SS/FF/FA plus WAHS-1 is a provisional record mapping only. Employer/issuer acceptance and climbing/rescue scope are not supplied and must be confirmed.",
            "identity": "Raw keeper codes, payroll references and names are identified separately. Integer-like payroll values may be normalized across leading-zero, decimal and scientific notation only; absent or conflicting identifiers remain explicit and clean attribution is never rewritten.",
            "action_dependencies": "Issuer verification precedes spending decisions; working-condition willingness is confirmed before courses; medical clearance precedes OSSC; verified OSSC-SS precedes WAHS. The posting funds renewals but does not define renewal routes or promise first-time training funding. Proposed employer checks are labelled recommendations.",
            "alternate_date_boundary": "The supplied current/leaver roster is a snapshot, not a reconstructed historical workforce. The explicit scenario date filters work, appraisal and training evidence; it does not reconstruct prior employment status.",
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
    brief_path = args.output_dir / "decision_brief.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(markdown_report(payload), encoding="utf-8")
    brief_path.write_text(decision_brief(payload), encoding="utf-8")
    print(
        json.dumps(
            {"json": str(json_path), "markdown": str(md_path), "decision_brief": str(brief_path), "summary": payload["summary"]},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
