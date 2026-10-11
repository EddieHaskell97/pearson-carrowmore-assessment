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
CURRENT = ROOT + "raw/personnel/cla_personnel_export.csv"
LEAVERS = ROOT + "raw/personnel/cla_personnel_leavers.csv"
OILEANN_NOTE = ROOT + "raw/appraisals/station_manager_notes/2011-nevisbeg-keeper-note.txt"
APPRAISALS = ROOT + "raw/appraisals/appraisals.jsonl"

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

# Appraisals are manager testimony, not observed competence. These deliberately
# narrow patterns surface only role-related testimony; every keeper-code-keyed
# row is reviewed, but irrelevant narrative is not repeated in the output.
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
}
APPRAISAL_SUPPORT_PATTERNS = {
    "go_to_person": re.compile(r"\bstation['’]s go-to\b", re.I),
    "made_proper_job": re.compile(r"\bmade a proper job of it\b", re.I),
    "resolved_failure": re.compile(r"\bwas the one who sorted it out\b", re.I),
    "trusted_by_manager": re.compile(r"\bhave come to rely on\b.*\bnever been let down\b", re.I),
    "explicit_capability": re.compile(r"\bgenuinely capable\b|\bcompetent\b", re.I),
    "good_standard": re.compile(r"\bto a good standard\b|\bproper standard\b", re.I),
    "sound": re.compile(r"\bis sound\b", re.I),
}

PRIMARY_APPRAISAL_TOPICS = {
    "electrical_or_controls",
    "mechanical_or_generating_plant",
    "height_or_access",
}
K1200_MATERIAL_LOG_IDS = {"CL005994", "CL007505", "CL009097", "CL009921"}


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
    return list(csv.DictReader(io.StringIO(text)))


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
        match = re.search(r"\b\d+(?:\.\d+)?\s*(psi|bar)\b", text, re.I)
        if match:
            flags.append(
                {
                    "code": "inconsistent_measurement_unit",
                    "observed": match.group(0),
                    "finding": "The quoted Megger reading uses a pressure unit, so the activity is retained but the numerical measurement is unreliable.",
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
    normalized = re.sub(r"\d+(?:\.\d+)?", "#", text.lower())
    normalized = re.sub(r"\bno\s*\.?\s*#", "no #", normalized)
    return re.sub(r"\W+", " ", normalized).strip()


def select_work_evidence(
    zf: zipfile.ZipFile, keeper: dict, entries: list[dict], as_of: date
) -> tuple[list[dict], dict]:
    """Review the complete clean history, then return a readable evidence sample."""
    candidates = []
    at_cutoff = [entry for entry in entries if parse_date(entry["date"]) <= as_of]
    for entry in entries:
        required_k1200 = keeper["keeper_code"] == "K1200" and entry["entry_id"] in K1200_MATERIAL_LOG_IDS
        if parse_date(entry["date"]) > as_of or (not ACTION_RE.search(entry["text"]) and not required_k1200):
            continue
        categories = entry_categories(entry["text"])
        if required_k1200 and not ({"electrical", "mechanical"} & set(categories)):
            categories.append("mechanical")
        if not ({"electrical", "mechanical"} & set(categories)):
            continue
        score = 2 * len({"electrical", "mechanical", "fault_finding", "permit_or_isolation"} & set(categories))
        score += len(set(categories))
        candidates.append((score, entry["date"], entry, categories))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]["entry_id"]), reverse=True)
    distinct, normalized_seen = [], set()
    for score, _, entry, categories in candidates:
        # Collapse superficial asset-number and measurement variants so repeated
        # synthetic templates do not masquerade as diverse experience.
        normalized = (
            f"material:{entry['entry_id']}"
            if keeper["keeper_code"] == "K1200" and entry["entry_id"] in K1200_MATERIAL_LOG_IDS
            else normalized_work_template(entry["text"])
        )
        if normalized in normalized_seen:
            continue
        corroboration = raw_corroboration(zf, entry, keeper)
        if not corroboration["resolved"]:
            raise ValueError(f"unresolved source reference {entry['source_record']}")
        distinct.append(
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
                "measurement_quality_flags": measurement_quality_flags(entry["text"]),
                "selection_score": score,
                "template_key": normalized,
            }
        )
        normalized_seen.add(normalized)

    # Five examples are normally sufficient for readability. K1200's four
    # named material entries are all retained because the appraisal directly
    # disputes what that log history represents.
    chosen = distinct[:5]
    if keeper["keeper_code"] == "K1200":
        required = [row for row in distinct if row["entry_id"] in K1200_MATERIAL_LOG_IDS]
        chosen = required + [row for row in chosen if row["entry_id"] not in K1200_MATERIAL_LOG_IDS]
        chosen = chosen[: max(5, len(required))]

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
        "category_coverage": category_coverage,
        "displayed_entry_ids": [row["entry_id"] for row in chosen],
        "interpretation": "The complete clean log history was screened. Repeated numeric and superficial wording variants were collapsed for decision quality; counts and repetition were not treated as competence.",
    }
    return chosen, review


def build_appraisal_review(rows: list[dict], as_of: date) -> dict:
    """Review exact keeper-code-keyed appraisals without name-only inference."""
    reviewed_ids, relevant, future_ids, same_year_uncertain = [], [], [], []
    for row in sorted(rows, key=lambda item: (item["year"], item["record_id"])):
        reviewed_ids.append(row["record_id"])
        relevant_sentences, topic_set, concern_set, support_set = [], set(), set(), set()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", row["text"]):
            sentence = sentence.strip()
            sentence_topics = {name for name, pattern in APPRAISAL_TOPIC_PATTERNS.items() if pattern.search(sentence)}
            sentence_concerns = {name for name, pattern in APPRAISAL_CONCERN_PATTERNS.items() if pattern.search(sentence)}
            sentence_supports = {name for name, pattern in APPRAISAL_SUPPORT_PATTERNS.items() if pattern.search(sentence)}
            # Signals and topics must co-occur in the same sentence. This avoids,
            # for example, attaching a paint-work criticism to a separate engine
            # compliment elsewhere in the appraisal.
            if sentence_topics and (sentence_concerns or sentence_supports):
                relevant_sentences.append(sentence)
                topic_set.update(sentence_topics)
                concern_set.update(sentence_concerns)
                support_set.update(sentence_supports)
        topics = sorted(topic_set)
        concerns = sorted(concern_set)
        supports = sorted(support_set)
        if row["year"] > as_of.year:
            future_ids.append(row["record_id"])
            temporal_use = "future_year_not_used"
        elif row["year"] == as_of.year:
            same_year_uncertain.append(row["record_id"])
            temporal_use = "same_year_timing_uncertain_context_only"
        else:
            temporal_use = "pre_cutoff_year"
        if topics and (concerns or supports):
            relevant.append(
                {
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
                    "decision_time_treatment": temporal_use,
                    "evidence_limit": "Manager testimony; useful for screening questions but not proof of competence, authorisation or the date of an event within the year.",
                }
            )
    material_concerns = [
        row
        for row in relevant
        if row["decision_time_treatment"] == "pre_cutoff_year"
        and row["year"] >= as_of.year - 10
        and row["concern_signals"]
        and PRIMARY_APPRAISAL_TOPICS.intersection(row["topics"])
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
        "keyed_rows_reviewed": len(rows),
        "reviewed_record_ids": reviewed_ids,
        "role_relevant_testimony": relevant,
        "role_relevant_testimony_count": len(relevant),
        "future_year_record_ids_not_used": future_ids,
        "same_year_record_ids_timing_uncertain": same_year_uncertain,
        "material_pre_cutoff_concern_ids": [row["record_id"] for row in material_concerns],
        "strong_manager_support_ids": [row["record_id"] for row in strong_support],
        "irrelevant_narrative_not_repeated": len(rows) - len(relevant),
    }


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


def build_training(keeper: dict, learnhub_rows: list[dict], scheme_map: dict, as_of: date) -> tuple[list[dict], list[dict]]:
    claims, future = [], []
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
                "interpretation": "The supplied module expiry and nominal scheme renewal rule are preserved separately; neither is silently substituted for the other.",
            }
            if claim["expiry_comparison"]["cutoff_status_disagrees"]:
                claim["status_at_cutoff"] = "pass_expiry_conflict_at_cutoff"
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


def recommendation_basis(
    evidence: list[dict], work_review: dict, appraisal_review: dict, recommendation: str
) -> tuple[str, dict]:
    categories = work_review["category_coverage"]
    concern_ids = appraisal_review["material_pre_cutoff_concern_ids"]
    support_ids = appraisal_review["strong_manager_support_ids"]
    criteria = {
        "qualifying_distinct_examples": work_review["distinct_qualifying_examples"],
        "category_coverage": categories,
        "cross_discipline_evidence": {"electrical", "mechanical"} <= set(categories),
        "fault_finding_evidence": "fault_finding" in categories,
        "material_pre_cutoff_appraisal_concern_ids": concern_ids,
        "strong_manager_support_ids": support_ids,
        "policy": {
            "supported_technical_interview": "At least five distinct relevant log examples and no explicit role-related appraisal concern in the ten years before the cutoff.",
            "targeted_screening_first": "Some relevant evidence exists, but it is sparse (fewer than five distinct examples) or recent explicit appraisal concerns require a focused screen before a full technical interview.",
            "insufficient_evidence": "Fewer than three distinct relevant examples and no strong keeper-code-keyed manager support.",
            "year_precision": "A 2026 year-only appraisal is context only because its position relative to 2026-10-11 is unknown.",
        },
        "ranking_used": False,
    }
    if recommendation == "outside_current_redeployment_cohort":
        return "The clean profile and leavers export mark this person as having left; no current redeployment pathway is assessed.", criteria
    if recommendation == "insufficient_evidence":
        return "The full clean history and exact keeper-code-keyed appraisals do not provide enough directly relevant, diverse evidence to support an interview decision; obtain specific plant-maintenance examples before reassessment.", criteria
    selected = []
    for category in ("fault_finding", "electrical", "mechanical", "permit_or_isolation"):
        item = next((row for row in evidence if category in row["categories"] and row not in selected), None)
        if item:
            selected.append(item)
        if len(selected) == 2:
            break
    if len(selected) < 2:
        selected.extend(row for row in evidence if row not in selected and len(selected) < 2)
    examples = "; ".join(f"{row['entry_id']} records “{row['text']}”" for row in selected)
    appraisal_clause = ""
    if concern_ids:
        appraisal_clause = f" Explicit role-related concerns in {', '.join(concern_ids)} remain unresolved."
    elif support_ids:
        appraisal_clause = f" Keeper-code-keyed manager testimony in {', '.join(support_ids[:2])} adds a screening lead, not proof of competence."
    if recommendation == "supported_technical_interview":
        conclusion = "The documented policy supports a structured technical interview, not competence, eligibility or appointment."
    else:
        conclusion = "Relevant experience is recorded, but the uncertainty should be tested in a targeted screen before deciding on a full technical interview."
    return f"{examples}.{appraisal_clause} {conclusion}", criteria


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
        return f"{module}: renew the expired Pass ({', '.join(expired)}); the posting says the employer funds renewals."
    not_achieved = [claim["record_id"] for claim in records if claim["status_at_cutoff"] == "not_achieved"]
    if not_achieved:
        return f"{module}: Not achieved in {', '.join(not_achieved)} is not a Pass; complete training and assessment if progression is approved (first-time funding is not promised)."
    attended = [claim["record_id"] for claim in records if claim["status_at_cutoff"] == "attended_not_passed"]
    if attended:
        return f"{module}: Attended in {', '.join(attended)} is not a Pass; establish the required passed assessment if progression is approved (first-time funding is not promised)."
    return f"{module}: no dated Pass is established; obtain the module if progression is approved (first-time funding is not promised)."


def ordered_actions(
    keeper: dict,
    claims: list[dict],
    conflicts: list[dict],
    recommendation: str,
    appraisal_review: dict,
    is_current: bool,
) -> tuple[list[str], list[str]]:
    if not is_current:
        return ["No current redeployment pathway is assessed for this leaver."], []
    concern_ids = appraisal_review["material_pre_cutoff_concern_ids"]
    if recommendation == "supported_technical_interview":
        source_phrase = "the cited logs and manager testimony" if appraisal_review["role_relevant_testimony_count"] else "the cited logs"
        initial = [f"Invite to a structured technical interview and use {source_phrase} as questions; assess fault diagnosis, safe isolation and hands-on plant maintenance rather than treating the records as proof."]
    elif recommendation == "targeted_screening_first":
        focus = f" Resolve the explicit concerns in {', '.join(concern_ids)}." if concern_ids else " Test the sparse or repetitive evidence with concrete examples."
        initial = [f"Run a targeted evidence screen before a full technical interview.{focus} Ask what the person did personally, what plant was involved, what checks controlled the work and what outcome was verified."]
    else:
        initial = ["Do not progress to a technical interview on the current evidence; first obtain independently checkable examples of hands-on electrical or mechanical plant maintenance."]
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
        f"After medical clearance, address the offshore-safety modules individually. {ossc_actions}",
        f"After OSSC-SS is issuer-verified current, address height safety because the supplied WAHS definition requires it. {height_action}",
        "Finally, complete the employer's permit, isolation and practical assessments before appointment or mobilisation.",
    ]
    return initial, later


def evaluate_keeper(zf, keeper, entries, appraisal_rows, learnhub_rows, scheme_map, as_of):
    evidence, work_review = select_work_evidence(zf, keeper, entries, as_of)
    appraisal_review = build_appraisal_review(appraisal_rows, as_of) if keeper["status"] == "current" else {
        "attribution_rule": "Leaver appraisals were not assessed because the person is outside the current cohort.",
        "keyed_rows_reviewed": 0,
        "reviewed_record_ids": [],
        "role_relevant_testimony": [],
        "role_relevant_testimony_count": 0,
        "future_year_record_ids_not_used": [],
        "same_year_record_ids_timing_uncertain": [],
        "material_pre_cutoff_concern_ids": [],
        "strong_manager_support_ids": [],
        "irrelevant_narrative_not_repeated": 0,
    }
    claims, future = build_training(keeper, learnhub_rows, scheme_map, as_of)
    conflicts = credential_conflicts(keeper, claims, as_of)
    coverage = safety_coverage(claims)
    categories = work_review["category_coverage"]
    is_current = keeper["status"] == "current"

    if not is_current:
        recommendation = "outside_current_redeployment_cohort"
        eligibility = "not_assessed_outside_current_cohort"
    elif work_review["distinct_qualifying_examples"] < 3 and not appraisal_review["strong_manager_support_ids"]:
        recommendation = "insufficient_evidence"
        eligibility = "not_established_from_bounded_evidence"
    elif work_review["distinct_qualifying_examples"] < 5 or appraisal_review["material_pre_cutoff_concern_ids"]:
        recommendation = "targeted_screening_first"
        eligibility = "plausible_but_essential_evidence_incomplete"
    else:
        recommendation = "supported_technical_interview"
        eligibility = "plausible_but_essential_evidence_incomplete"
    reason, recommendation_criteria = recommendation_basis(evidence, work_review, appraisal_review, recommendation)
    initial_actions, later_actions = ordered_actions(keeper, claims, conflicts, recommendation, appraisal_review, is_current)
    actions = initial_actions + later_actions
    limitations = [
        {"code": "competence_not_inferred", "text": "Examples support interview potential only; tags, grades, hours and occurrence counts were not treated as proof of competence."},
    ]
    if is_current:
        limitations.append({"code": "medical_not_supplied", "text": "No current offshore medical evidence is present in the bounded sources."})
    supplementary = []
    chronology_conflicts = []
    if keeper["keeper_code"] == "K1538":
        switching_entry = next(e for e in entries if e["entry_id"] == "CL006360")
        switching_raw = raw_corroboration(zf, switching_entry, keeper)
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
                "attribution_basis": "The note names NI GHARBHAIL O/Oileann and the personnel export has one exact NI GHARBHAIL O match. The clean profile places K1538 at Nevisbeg in 2011, but the note's claimed eleven-year station tenure conflicts with the recorded chronology.",
                "use": "interview_lead_only",
            }
        )
        chronology_conflicts.append(
            {
                "code": "oileann_station_tenure_conflict",
                "finding": "The 2011 note says Oileann had been at Nevisbeg for eleven years (implying about 2000), while the clean profile records joining in 1998 and a Nevisbeg posting beginning in 2009. The testimony is retained as an interview lead, but its station-tenure chronology is not established.",
                "source_references": [
                    "raw/appraisals/station_manager_notes/2011-nevisbeg-keeper-note.txt#L2,L3,L7",
                    "clean/keepers.json#K1538/date_joined",
                    "clean/keepers.json#K1538/postings/NEV",
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
        "work_history_review": work_review,
        "relevant_experience": evidence,
        "appraisal_review": appraisal_review,
        "supplementary_evidence": supplementary,
        "identity_and_chronology_conflicts": chronology_conflicts,
        "experience_categories": categories,
        "credential_claims": claims,
        "clean_certification_summaries": clean_summaries(keeper),
        "credential_conflicts": conflicts,
        "future_evidence_not_used": future,
        "essential_coverage_from_dated_passes": coverage,
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
        "## Current-keeper comparison",
        "",
        "| ID / name | Decision | Strongest evidence | Main uncertainty | Immediate next action |",
        "|---|---|---|---|---|",
    ]
    for row in sorted(current_rows, key=lambda item: item["keeper_code"]):
        evidence_ids = [item["entry_id"] for item in row["relevant_experience"][:2]]
        support_ids = row["appraisal_review"]["strong_manager_support_ids"][:1]
        strongest = ", ".join(evidence_ids + support_ids) or "No direct evidence"
        concerns = row["appraisal_review"]["material_pre_cutoff_concern_ids"]
        if concerns:
            uncertainty = "Unresolved " + ", ".join(concerns)
        elif row["work_history_review"]["distinct_qualifying_examples"] < 5:
            uncertainty = f"Only {row['work_history_review']['distinct_qualifying_examples']} distinct log patterns"
        elif row["appraisal_review"]["same_year_record_ids_timing_uncertain"]:
            uncertainty = "2026 appraisal timing uncertain"
        elif not row["appraisal_review"]["reviewed_record_ids"]:
            uncertainty = "No keyed appraisal"
        else:
            uncertainty = "Manager testimony unverified; mobilisation gates open"
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
        lines.extend([
            f"## {row['keeper_code']} — {row['name_ascii'] or row['name']}",
            "",
            f"- Interview: `{row['interview_recommendation']}` — {row['recommendation_reason']}",
            f"- Application eligibility: `{row['application_eligibility']}`",
            f"- Mobilisation readiness: `{row['mobilisation_readiness']}`",
            f"- Relevant evidence categories: {', '.join(row['experience_categories']) or 'none found'}",
            f"- Full clean log review: {row['work_history_review']['source_entry_count']} rows; {row['work_history_review']['distinct_qualifying_examples']} distinct relevant patterns after template collapse.",
            f"- Appraisal review: {row['appraisal_review']['keyed_rows_reviewed']} exact keeper-code-keyed rows; {row['appraisal_review']['irrelevant_narrative_not_repeated']} non-role-relevant rows not repeated.",
            "",
        ])
        if row["relevant_experience"]:
            lines.append("Evidence:")
            lines.append("")
        material_appraisals = [
            item for item in row["appraisal_review"]["role_relevant_testimony"]
            if item["record_id"] in set(row["appraisal_review"]["material_pre_cutoff_concern_ids"] + row["appraisal_review"]["strong_manager_support_ids"])
        ]
        if material_appraisals:
            lines.extend(["Manager testimony used as screening context:", ""])
            for item in material_appraisals:
                signal = []
                if item["support_signals"]:
                    signal.append("support: " + ", ".join(item["support_signals"]))
                if item["concern_signals"]:
                    signal.append("concern: " + ", ".join(item["concern_signals"]))
                excerpt = " / ".join(item["role_relevant_excerpt"])
                lines.append(f"- {item['year']} (year precision) — {excerpt} ({item['record_id']}; `{item['source_reference']}`; {'; '.join(signal)}). Manager testimony only, not competence or authorisation.")
            lines.append("")
        uncertain_appraisals = row["appraisal_review"]["same_year_record_ids_timing_uncertain"]
        if uncertain_appraisals:
            lines.append(f"- Same-year timing uncertainty: {', '.join(uncertain_appraisals)} are dated only to 2026, so they are context-only and do not establish a fact before 2026-10-11.")
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
                lines.append(f"- {e['date']} — “{e['text']}” ({e['entry_id']}; `{e['source_reference']}`; {attribution}).")
                for flag in e["measurement_quality_flags"]:
                    lines.append(f"  - Measurement warning `{flag['code']}`: {flag['finding']} Observed: `{flag['observed']}`.")
            lines.append("")
        for e in row["supplementary_evidence"]:
            lines.append(f"- Supplementary note: {e['claim']} (`{e['source_reference']}`). {e['attribution_basis']} This is an interview lead, not an authorisation.")
            if e.get("supporting_entry"):
                s = e["supporting_entry"]
                lines.append(f"- Hand-check entry: {s['date']} — “{s['text']}” ({s['entry_id']}; `{s['source_reference']}`).")
            lines.append("")
        for conflict in row["identity_and_chronology_conflicts"]:
            lines.append(f"- Chronology conflict `{conflict['code']}`: {conflict['finding']}")
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
            ids = ", ".join(x["record_id"] for x in row["future_evidence_not_used"])
            lines.append(f"- Future at cutoff and not used: {ids}.")
        lines.extend(["", "Initial selection action:", ""])
        for action in row["initial_selection_actions"]:
            lines.append(f"- {action}")
        lines.extend(["", "Later qualification and mobilisation actions (only after selection progression):", ""])
        for action in row["later_qualification_and_mobilisation_actions"]:
            lines.append(f"- {action}")
        lines.append("")
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
                by_keeper_logs[k["keeper_code"]],
                by_keeper_appraisals[k["keeper_code"]],
                by_keeper_training[k["keeper_code"]],
                scheme_map,
                as_of,
            )
            for k in sorted(keepers, key=lambda x: x["keeper_code"])
        ]
    counts = Counter(c["interview_recommendation"] for c in candidates)
    return {
        "schema_version": 3,
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
            "supported_technical_interview": counts["supported_technical_interview"],
            "targeted_screening_first": counts["targeted_screening_first"],
            "insufficient_evidence": counts["insufficient_evidence"],
            "outside_current_cohort": counts["outside_current_redeployment_cohort"],
            "appraisal_source_rows": len(appraisals),
            "appraisal_rows_with_keeper_code": sum(bool(row.get("keeper_code")) for row in appraisals),
            "appraisal_rows_without_keeper_code_unattached": sum(not row.get("keeper_code") for row in appraisals),
            "appraisal_rows_reviewed_for_current_cohort": sum(c["appraisal_review"]["keyed_rows_reviewed"] for c in candidates),
        },
        "method": {
            "work_evidence": "Every clean log entry for each profile is reviewed. An entry normally needs an explicit maintenance action plus an electrical or mechanical plant term; superficial numeric/template variants are collapsed. Up to five strongest examples are shown, except named material records needed to explain a conflict. Counts, hours and repetition are not competence.",
            "appraisals": "Every appraisal carrying an exact current-cohort keeper_code is reviewed. Name-only/null-key rows are not attached. Only role-relevant testimony is repeated. Year-only 2026 records are context-only because their timing relative to 2026-10-11 is unknown; future years are excluded from conclusions.",
            "decision_categories": "supported_technical_interview; targeted_screening_first; insufficient_evidence; outside_current_redeployment_cohort. The categories are rule-based gates, not a score or ranking.",
            "supported_technical_interview": "At least five distinct relevant log examples and no explicit role-related appraisal concern in the ten years before the cutoff.",
            "targeted_screening_first": "Relevant evidence exists, but it is sparse or explicit recent role-related appraisal concerns need focused resolution before a full technical interview.",
            "insufficient_evidence": "Fewer than three distinct relevant log examples and no strong keeper-code-keyed manager support.",
            "training": "Dated LearnHub outcome and supplied expiry are evaluated at the explicit cutoff. Pass, Attended and Not achieved remain distinct. A nominal scheme-rule date is also shown; when it changes cutoff status, neither date is chosen and issuer verification is required.",
            "height_mapping": "WAHS-1 is used as the supplied definition's direct height-safety module. This is a documented interpretation because the posting asks for a combined offshore certificate while OSSC itself has no height module.",
            "identity": "Raw keeper codes, payroll references and names are identified separately. Integer-like payroll values may be normalized across leading-zero, decimal and scientific notation only; absent or conflicting identifiers remain explicit and clean attribution is never rewritten.",
            "action_dependencies": "Issuer verification precedes spending decisions; working-condition willingness is confirmed before courses; medical clearance precedes OSSC; verified OSSC-SS precedes WAHS. The posting funds renewals but does not promise first-time training funding.",
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
