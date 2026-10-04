"""SEBI registration, entity-name, and link consistency checks."""
from __future__ import annotations

import re
import json
import sqlite3
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import ollama

from fraud_vision import analyze_evidence, analyze_evidence_structured
from indic_evidence import phonetic_search_text


DB_PATH = Path(__file__).with_name("scam_database.db")
OFFICIAL_DOMAINS_PATH = Path(__file__).with_name("official_domains.json")
COMPANY_STOPWORDS = {
    "the", "and", "of", "pvt", "private", "ltd", "limited", "co", "company",
    "services", "service", "advisors", "adviser", "advisers", "advisory", "management",
    "financial", "finance", "securities", "capital", "asset", "assets", "markets", "market",
}


def _clean(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def _unique(values):
    result = []
    seen = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean.casefold() not in seen:
            result.append(clean)
            seen.add(clean.casefold())
    return result


def _unique_names(values):
    result = []
    seen = set()
    for value in values:
        clean = " ".join(str(value).strip().split())
        key = _clean(clean)
        if clean and key and key not in seen:
            result.append(clean)
            seen.add(key)
    return result


def _name_matches(claimed: str, official: str, username: str) -> bool:
    claimed_clean = _clean(claimed)
    official_clean = _clean(official)
    username_clean = _clean(username)
    claimed_phonetic = _clean(phonetic_search_text(claimed))
    official_phonetic = _clean(phonetic_search_text(official))
    claimed_clean = claimed_phonetic or claimed_clean
    official_clean = official_phonetic or official_clean
    if not claimed_clean:
        return False
    if claimed_clean in official_clean or official_clean in claimed_clean:
        return True
    if username_clean and (claimed_clean in username_clean or username_clean in claimed_clean):
        return True
    claimed_tokens = {part for part in claimed_clean.split() if len(part) >= 3 and part not in COMPANY_STOPWORDS}
    official_tokens = {part for part in official_clean.split() if len(part) >= 3 and part not in COMPANY_STOPWORDS}
    username_tokens = {part for part in username_clean.split() if len(part) >= 3}
    official_aliases = official_tokens | username_tokens
    overlap = claimed_tokens & official_aliases
    if overlap and (len(claimed_tokens) == 1 or len(overlap) / len(claimed_tokens) >= 0.5):
        return True
    compact_claim = claimed_clean.replace(" ", "")
    compact_official = official_clean.replace(" ", "")
    return SequenceMatcher(None, compact_claim, compact_official).ratio() >= 0.82


def _registered_domains(sebi_number: str) -> list[str]:
    try:
        data = json.loads(OFFICIAL_DOMAINS_PATH.read_text(encoding="utf-8"))
        entry = data.get(sebi_number.upper(), {})
        return [str(domain).lower().strip(".") for domain in entry.get("domains", []) if domain]
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        return []


def _registered_aliases(sebi_number: str) -> list[str]:
    try:
        data = json.loads(OFFICIAL_DOMAINS_PATH.read_text(encoding="utf-8"))
        entry = data.get(sebi_number.upper(), {})
        aliases = entry.get("aliases", [])
        return [str(alias).strip() for alias in aliases if alias]
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        return []


@lru_cache(maxsize=1)
def _registry_name_rows():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT sebi_number, username, official_entity FROM sebi_records").fetchall()
        domain_data = json.loads(OFFICIAL_DOMAINS_PATH.read_text(encoding="utf-8"))
        aliases_by_entity = {}
        for entry in domain_data.values():
            if isinstance(entry, dict):
                aliases_by_entity.setdefault(_clean(entry.get("entity", "")), []).extend(entry.get("aliases", []))
        output = []
        for number, username, entity in rows:
            aliases = aliases_by_entity.get(_clean(entity), [])
            output.append((str(number or ""), str(username or ""), str(entity or ""), tuple(map(str, aliases))))
        return tuple(output)
    except (OSError, sqlite3.Error, json.JSONDecodeError, AttributeError, TypeError):
        return ()


def _registered_names_in_text(text: str) -> list[str]:
    source = f" {_clean(text)} "
    phonetic_source = f" {_clean(phonetic_search_text(text))} "
    matches = []
    for _number, _username, entity, aliases in _registry_name_rows():
        # Generic account labels such as "research" or "advisor" are not
        # identities. Only accept a full registered entity or explicit alias.
        candidates = (entity, *aliases)
        if any(
            (clean := _clean(candidate))
            and len(clean) >= 5
            and (f" {clean} " in source or f" {clean} " in phonetic_source
                 or f" {_clean(phonetic_search_text(candidate))} " in phonetic_source)
            for candidate in candidates
        ):
            matches.append(entity)
    return _unique(matches)


def _registered_records_for_name(name: str):
    cleaned = _clean(phonetic_search_text(name)) or _clean(name)
    if not cleaned:
        return []
    meaningful_tokens = [token for token in cleaned.split() if len(token) >= 3 and token not in COMPANY_STOPWORDS]
    matches = []
    for number, username, entity, aliases in _registry_name_rows():
        candidates = (entity, username, *aliases)
        candidate_names = [
            normalized for candidate in candidates if candidate
            for normalized in (_clean(candidate), _clean(phonetic_search_text(candidate)))
            if normalized
        ]
        exact_match = cleaned in candidate_names
        substantial_match = len(cleaned) >= 7 and len(meaningful_tokens) >= 2 and any(
            (cleaned in candidate or candidate in cleaned) and abs(len(cleaned) - len(candidate)) <= 12
            or SequenceMatcher(None, cleaned, candidate).ratio() >= 0.92
            for candidate in candidate_names
        )
        if exact_match or substantial_match:
            matches.append((number, username, entity))
    return matches


def _link_matches(url: str, official_domains: list[str]) -> bool:
    candidate = url.strip()
    parsed = urlparse(candidate if "://" in candidate else "https://" + candidate)
    host = (parsed.hostname or "").casefold().strip(".")
    if not host:
        return False
    for domain in official_domains:
        trusted = domain.casefold().strip(".")
        if host == trusted or host.endswith("." + trusted):
            return True
    return False


def _extract_urls(text: str) -> list[str]:
    pattern = r"(?i)(?:\b(?:https?://|www\.)[^\s<>\"')\]]+|(?<![@\w.-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}(?::\d+)?(?:/[^\s<>\"')\]]*)?)"
    return _unique(re.findall(pattern, text or ""))


class ScamVerifier:
    def __init__(self, client=None):
        self.client = client or ollama.Client()

    def analyze_evidence_details(self, input_text="", claimed_username="", file_path=None):
        return analyze_evidence_structured(
            input_text=input_text,
            claimed_username=claimed_username,
            file_path=file_path,
            client=self.client,
        )

    def analyze_evidence(self, input_text="", claimed_username="", file_path=None):
        return analyze_evidence(input_text, claimed_username, file_path, self.client)

    @staticmethod
    def query_database(sebi_number: str):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username, official_entity FROM sebi_records WHERE upper(sebi_number) = ?",
                (sebi_number.upper(),),
            )
            return cursor.fetchone()

    @staticmethod
    def nearby_database_records(sebi_number: str):
        """Find one-character OCR candidates; caller must confirm the company name too."""
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT sebi_number, username, official_entity FROM sebi_records WHERE length(sebi_number) BETWEEN ? AND ?",
                (max(1, len(sebi_number) - 1), len(sebi_number) + 1),
            ).fetchall()
        ranked = [
            (SequenceMatcher(None, sebi_number.upper(), row[0].upper()).ratio(), row)
            for row in rows
        ]
        return sorted((item for item in ranked if item[0] >= 0.90), key=lambda item: item[0], reverse=True)

    def _comparison_report(self, numbers, company_names, urls, claimed_username, evidence_handles, evidence_sources):
        """Build explicit per-item and cartesian evidence checks for the UI."""
        number_values = list(numbers) or [None]
        name_values = list(company_names) or [None]
        records = {number: self.query_database(number) for number in numbers}
        lookup_names = _unique_names(
            list(company_names)
            + ([claimed_username] if claimed_username else [])
            + list(evidence_handles)
        )
        name_lookup_records = {name: _registered_records_for_name(name) for name in lookup_names if name}
        registration_checks = []
        for number in numbers:
            record = records[number]
            registration_checks.append({
                "sebi_number": number,
                "status": "GREEN" if record else "RED",
                "registered_username": record[0] if record else None,
                "official_entity": record[1] if record else None,
                "explanation": (
                    f"{number} is present in the local SEBI registration database as {record[1]} ({record[0]})."
                    if record else f"{number} was not found in the local SEBI registration database."
                ),
            })

        identity_combinations = []
        for number in number_values:
            record = records.get(number) if number else None
            for name in name_values:
                if number is None:
                    candidates = name_lookup_records.get(name, []) if name else []
                    matches = bool(candidates)
                    status = "YELLOW" if matches else "RED"
                    matched_records = "; ".join(f"{entity} ({candidate_id})" for candidate_id, _username, entity in candidates)
                    explanation = (
                        f"Name matches registry record(s): {matched_records}, but no SEBI ID was present in the supplied evidence."
                        if matches else "No SEBI registration number was extracted and this name did not match a local registration."
                    )
                elif record is None:
                    status = "RED"
                    matches = False
                    explanation = f"SEBI ID {number} is not registered in the local database."
                elif name is None:
                    status = "YELLOW"
                    matches = False
                    explanation = f"SEBI ID {number} is registered as {record[1]}, but no name was extracted to compare."
                else:
                    matches = _name_matches(name, record[1], record[0]) or any(
                        _name_matches(name, alias, record[0]) for alias in _registered_aliases(number)
                    )
                    status = "GREEN" if matches else "YELLOW"
                    explanation = (
                        f"{name} matches the registered entity {record[1]} for {number}."
                        if matches else f"{name} does not match the registered entity {record[1]} for {number}."
                    )
                identity_combinations.append({
                    "sebi_number": number,
                    "name": name,
                    "status": status,
                    "matches_registered_entity": matches,
                    "explanation": explanation,
                    "evidence_sources": evidence_sources,
                })

        username_checks = []
        username_values = []
        if claimed_username:
            username_values.append((claimed_username, "entered name/username"))
        for handle in evidence_handles:
            if _clean(handle) not in {_clean(value) for value, _kind in username_values}:
                username_values.append((handle, "extracted handle"))
        for username_value, username_type in username_values:
            for number in number_values:
                record = records.get(number) if number else None
                if not number or not record:
                    candidates = _registered_records_for_name(username_value)
                    matches = bool(candidates)
                    status = "YELLOW" if matches else "RED"
                    explanation = (
                        "This name matches a local registry record, but no SEBI ID was present in the supplied evidence."
                        if matches else "No verified SEBI registration is available to check this supplied name/username."
                    )
                else:
                    allowed_handles = {
                        re.sub(r"[^a-z0-9]", "", alias.casefold().removeprefix("@"))
                        for alias in (record[0], record[1], *_registered_aliases(number)) if alias
                    }
                    normalized_handle = re.sub(r"[^a-z0-9]", "", username_value.casefold().removeprefix("@"))
                    matches = (
                        _name_matches(username_value, record[1], record[0])
                        or any(_name_matches(username_value, alias, record[0]) for alias in _registered_aliases(number))
                        or normalized_handle in allowed_handles
                    )
                    status = "GREEN" if matches else "YELLOW"
                    explanation = (
                        f"{username_value} matches the registered name/username for {number}."
                        if matches else f"{username_value} does not match the registered name/username for {number}."
                    )
                username_checks.append({
                    "sebi_number": number,
                    "claimed_username": username_value,
                    "username_type": username_type,
                    "status": status,
                    "matches_registered_entity": matches,
                    "explanation": explanation,
                    "evidence_sources": evidence_sources,
                })

        urls_checked = []
        url_combinations = []
        url_name_values = [(name, "extracted name") for name in company_names]
        url_identity_keys = {_clean(name) for name in company_names}
        for handle in evidence_handles:
            if _clean(handle) not in url_identity_keys:
                url_name_values.append((handle, "extracted handle"))
                url_identity_keys.add(_clean(handle))
        if claimed_username and _clean(claimed_username) not in url_identity_keys:
            url_name_values.append((claimed_username, "entered name/username"))
        if not url_name_values:
            url_name_values = [(None, None)]
        url_number_values = list(numbers)
        if not url_number_values:
            for candidates in name_lookup_records.values():
                url_number_values.extend(candidate[0] for candidate in candidates)
            url_number_values = _unique(url_number_values)
        url_records = dict(records)
        for number in url_number_values:
            if number not in url_records:
                candidate = next(
                    (item for values in name_lookup_records.values() for item in values if item[0] == number),
                    None,
                )
                if candidate:
                    url_records[number] = (candidate[1], candidate[2])
        for url in urls:
            combinations = []
            for number in url_number_values or [None]:
                record = url_records.get(number) if number else None
                for name, name_type in url_name_values:
                    if not number or not record:
                        id_matches = False
                        name_matches = False if name else None
                        domain_matches = False
                        status = "RED"
                        explanation = "No verified SEBI registration number is available for this URL."
                    else:
                        id_matches = number in records
                        name_matches = (
                            _name_matches(name, record[1], record[0])
                            or any(_name_matches(name, alias, record[0]) for alias in _registered_aliases(number))
                            if name else None
                        )
                        domain_matches = _link_matches(url, _registered_domains(number))
                        pair_matches = domain_matches and name_matches is not False
                        if not domain_matches:
                            status = "YELLOW"
                            domains = _registered_domains(number)
                            explanation = (
                                f"{url} does not match the trusted domain(s) {', '.join(domains)} for {record[1]} ({number})."
                                if domains else f"No trusted domain is configured for {record[1]} ({number}); {url} could not be verified."
                            )
                        elif name_matches is False:
                            status = "YELLOW"
                            explanation = f"The URL domain matches {record[1]} ({number}), but the paired name {name} does not match that registration."
                        elif not id_matches:
                            status = "YELLOW"
                            explanation = f"{url} and {name or record[1]} match {record[1]} ({number}), but this SEBI ID was found by name lookup and was not present in the submitted evidence."
                        elif domain_matches:
                            status = "GREEN"
                            explanation = f"{url} matches the registered domain for {record[1]} ({number})" + (f" and {name} matches the registration." if name else ".")
                    combination = {
                        "url": url,
                        "sebi_number": number,
                        "name": name,
                        "name_type": name_type,
                        "status": status,
                        "matches_registered_entity": bool(record and (pair_matches if number in url_records else False)),
                        "id_matches_registry": id_matches,
                        "sebi_number_in_evidence": bool(number and number in numbers),
                        "name_matches_registration": name_matches,
                        "domain_matches_registration": domain_matches,
                        "explanation": explanation,
                        "evidence_sources": evidence_sources,
                    }
                    combinations.append(combination)
                    url_combinations.append(combination)
            matched = any(item["matches_registered_entity"] for item in combinations)
            has_domain_match = any(item["domain_matches_registration"] for item in combinations)
            has_explicit_domain_mismatch = any(
                item["sebi_number_in_evidence"] and item["id_matches_registry"] and not item["domain_matches_registration"]
                for item in combinations
            )
            has_unverified_id_pair = any(item["status"] == "RED" for item in combinations)
            has_explicit_match = any(item["matches_registered_entity"] and item["sebi_number_in_evidence"] for item in combinations)
            status = "GREEN" if has_explicit_match else (
                "YELLOW" if matched or has_domain_match else (
                    "RED" if has_explicit_domain_mismatch or has_unverified_id_pair or not url_number_values else "YELLOW"
                )
            )
            urls_checked.append({
                "url": url,
                "status": status,
                "matches_registered_entity": matched,
                "explanation": (
                    f"At least one supplied SEBI number/name combination matches this URL ({sum(item['matches_registered_entity'] for item in combinations)} matching combination(s))."
                    if has_explicit_match else (
                        f"This URL matches a company found by name lookup ({sum(item['matches_registered_entity'] for item in combinations)} matching combination(s)), but the corresponding SEBI ID was not present in the submitted evidence."
                        if matched else "No SEBI number/name combination verified this URL against a trusted company domain."
                    )
                ),
                "combinations": combinations,
                "evidence_sources": evidence_sources,
            })

        return {
            "extracted_urls": list(urls),
            "extracted_sebi_numbers": list(numbers),
            "extracted_names": list(company_names),
            "name_registry_matches": [
                {
                    "name": name,
                    "registrations": [
                        {"sebi_number": number, "registered_username": username, "official_entity": entity}
                        for number, username, entity in matches
                    ],
                }
                for name, matches in name_lookup_records.items()
            ],
            "registration_checks": registration_checks,
            "name_checks": identity_combinations,
            "username_checks": username_checks,
            "urls_checked": urls_checked,
            "url_combinations": url_combinations,
        }

    def verify(self, input_text="", claimed_username="", analysis_text="", evidence=None):
        evidence = evidence if isinstance(evidence, dict) else {}
        parsed_analysis = {}
        if analysis_text:
            try:
                parsed = json.loads(analysis_text)
                if isinstance(parsed, dict):
                    parsed_analysis = parsed
            except (json.JSONDecodeError, TypeError):
                pass
        source_text = "\n".join(part for part in (
            input_text,
            evidence.get("extracted_text", ""),
            parsed_analysis.get("extracted_text", ""),
            analysis_text if not parsed_analysis else "",
        ) if part)
        found_numbers = re.findall(r"\bIN[A-Z]\d{6,11}\b|\bIN/AIF[A-Z0-9/\-]{6,18}\b", source_text.upper())
        numbers = _unique(evidence.get("sebi_registration_numbers", []) + found_numbers)
        registration_entities = evidence.get("registration_entities", {})
        if not isinstance(registration_entities, dict):
            registration_entities = {}
        registration_entities = {str(number).upper(): str(entity).strip() for number, entity in registration_entities.items() if str(entity).strip()}
        company_names = _unique_names(
            list(evidence.get("registered_company_names", []))
            + list(registration_entities.values())
            + _registered_names_in_text(source_text)
        )
        urls = _unique(evidence.get("urls", []) + _extract_urls(source_text))
        evidence_handles = evidence.get("handles", [])
        if isinstance(evidence_handles, str):
            evidence_handles = [evidence_handles]
        elif not isinstance(evidence_handles, list):
            evidence_handles = []
        evidence_handles = _unique(evidence_handles)
        handles = _unique(evidence_handles + ([claimed_username] if claimed_username else []))
        ai_flags = _unique(evidence.get("red_flags", []) + evidence.get("visual_anomalies", []))
        evidence_sources = evidence.get("evidence_sources", [])
        if not isinstance(evidence_sources, list):
            evidence_sources = []
        comparison_report = self._comparison_report(numbers, company_names, urls, claimed_username, evidence_handles, evidence_sources)

        def finish(*args):
            result = self._result(*args)
            result.update(comparison_report)
            return result

        if not numbers:
            ai_flags = [
                flag for flag in ai_flags
                if not re.search(r"no (?:valid )?sebi registration number|no registration number", str(flag), re.I)
            ]
        if not numbers and not company_names:
            missing_reason = "No SEBI registration number or company/adviser name could be extracted. Treat this evidence as HIGH RISK until independently verified."
            return finish("RED", "🔴 HIGH RISK — NO REGISTRATION DETAILS", missing_reason, None, None, [], urls, ai_flags + [missing_reason], handles)

        if not numbers:
            reason = "A company/adviser name is visible, but no SEBI registration number was found. The registration cannot be verified; treat the claim as high risk."
            return finish("RED", "🔴 HIGH RISK — NO SEBI NUMBER", reason, None, None, [], urls, ai_flags + [reason], handles)

        records = []
        unknown_ids = []
        for number in numbers:
            record = self.query_database(number)
            if record:
                records.append((number, record[0], record[1]))
            else:
                # A similar-looking number is still unverified. Do not silently
                # replace a supplied registration ID with a nearby database ID.
                unknown_ids.append(number)
        if unknown_ids:
            reason = "SEBI registration ID(s) not present in the local database: " + ", ".join(unknown_ids) + ". Confirm with SEBI before trusting this document."
            return finish("RED", "🔴 HIGH RISK — UNMATCHED SEBI ID", reason, numbers[0], None, records, urls, ai_flags + [reason], handles)

        link_checks = comparison_report["urls_checked"]
        entity_mismatches = []
        link_mismatches = [item["url"] for item in link_checks if item.get("status") == "RED"]
        handle_mismatches = []
        unassociated_numbers = []
        # This field may contain a company or SEBI-listed contact name as well
        # as a social handle. If it exactly maps to one of the registrations in
        # the evidence, associate it with that record instead of treating it as
        # a handle that must match every other registration in the document.
        claimed_name_numbers = set()
        if claimed_username:
            for number, username, official_entity in records:
                aliases = _registered_aliases(number)
                if (
                    _name_matches(claimed_username, official_entity, username)
                    or any(_name_matches(claimed_username, alias, username) for alias in aliases)
                ):
                    claimed_name_numbers.add(number.upper())
        for number, username, official_entity in records:
            source_scoped_name = registration_entities.get(number.upper())
            scoped_name = source_scoped_name or (claimed_username if number.upper() in claimed_name_numbers else None)
            compare_identity = bool(scoped_name) or len(numbers) == 1
            supplied_handle = _clean(claimed_username).replace(" ", "")
            registered_aliases = _registered_aliases(number)
            allowed_handles = {
                re.sub(r"[^a-z0-9]", "", alias.casefold())
                for alias in (username or "", official_entity or "", *registered_aliases)
                if alias
            }
            if compare_identity and supplied_handle and not claimed_name_numbers and supplied_handle.removeprefix("@") not in allowed_handles:
                handle_mismatches.append(claimed_username)
            for visible_handle in evidence_handles:
                normalized_handle = re.sub(r"[^a-z0-9]", "", str(visible_handle).casefold().removeprefix("@"))
                if compare_identity and normalized_handle and normalized_handle not in allowed_handles:
                    handle_mismatches.append(str(visible_handle))
            if scoped_name:
                names_to_check = [scoped_name]
            elif len(numbers) == 1:
                names_to_check = company_names
                if not names_to_check:
                    entity_mismatches.append("Company/adviser name not readable")
            elif not company_names:
                names_to_check = []
                entity_mismatches.append("Company/adviser name not readable")
            else:
                # Several registrations may belong to unrelated organisations.
                # Never compare every name to every ID when the evidence doesn't
                # establish which name belongs to which registration.
                names_to_check = []
                unassociated_numbers.append(number)
            mismatching_names = [name for name in names_to_check if not _name_matches(name, official_entity, username)]
            if mismatching_names:
                entity_mismatches.extend(mismatching_names)

        supplied_username_checks = comparison_report.get("username_checks", [])
        if claimed_username and supplied_username_checks and not any(
            check.get("matches_registered_entity") for check in supplied_username_checks
        ):
            handle_mismatches.append(claimed_username)

        if entity_mismatches:
            reason = "The company/adviser name in the evidence is missing or does not match the entity registered for the supplied SEBI number."
            link_flags = [f"Untrusted URL domain: {url}" for url in link_mismatches]
            return finish("YELLOW", "🟡 REVIEW — NAME DOES NOT MATCH", reason, numbers[0], records[0][2], records, urls, ai_flags + [reason] + entity_mismatches + link_flags, handles, link_checks)
        if handle_mismatches:
            reason = "The supplied account handle does not match the username associated with this SEBI registration in the local database. This is an impersonation red flag."
            link_flags = [f"Untrusted URL domain: {url}" for url in link_mismatches]
            return finish("YELLOW", "🟡 REVIEW — USERNAME MISMATCH", reason, numbers[0], records[0][2], records, urls, ai_flags + [reason] + handle_mismatches + link_flags, handles, link_checks)
        if link_mismatches:
            reason = "One or more supplied links do not match the company registered under the supplied SEBI number. Do not open or trust those links."
            return finish("RED", "🔴 HIGH RISK — LINK MISMATCH", reason, numbers[0], records[0][2], records, urls, ai_flags + [reason] + link_mismatches, handles, link_checks)

        verdict = evidence.get("verdict", "").upper()
        if verdict == "HIGH RISK" or ai_flags:
            reason = "The registration and visible entity details match, but the document still contains separate fraud or visual-anomaly indicators."
            return finish("RED", "🔴 HIGH RISK — DOCUMENT RED FLAGS", reason, numbers[0], records[0][2], records, urls, ai_flags, handles, link_checks)

        if unassociated_numbers:
            reason = "The named entity matches its associated SEBI registration, but additional SEBI ID(s) were found without a nearby entity label: " + ", ".join(unassociated_numbers) + ". They were not compared against the named company."
            return finish("YELLOW", "🟡 ADDITIONAL ID NEEDS CONTEXT", reason, numbers[0], records[0][2], records, urls, ai_flags, handles, link_checks)

        if not company_names:
            reason = "The SEBI number exists in the local database, but a company/adviser name was not readable for comparison."
            return finish("YELLOW", "🟡 NEEDS REVIEW", reason, numbers[0], records[0][2], records, urls, ai_flags, handles, link_checks)

        if not urls and not handles and not evidence.get("claims") and not claimed_username:
            reason = "The registration number and name match the local database, but the image does not show a profile link, handle, or claim to verify. This does not authenticate the pictured profile or person."
            return finish("YELLOW", "🟡 REGISTRATION MATCH — PROFILE UNVERIFIED", reason, numbers[0], records[0][2], records, urls, ai_flags, handles, link_checks)

        reason = "SEBI number and company name match the local registration database. This does not prove that the account or linked content is genuine."
        return finish("GREEN", "🟢 REGISTRATION MATCH", reason, numbers[0], records[0][2], records, urls, ai_flags, handles, link_checks)

    @staticmethod
    def _result(status, badge, reason, sebi_number, official_entity, records, urls, flags, handles, link_checks=None):
        return {
            "status": status,
            "badge": badge,
            "reason_en": reason,
            "reason_hi": reason,
            "sebi_number": sebi_number,
            "official_entity": official_entity,
            "registrations_checked": [
                {"sebi_number": number, "registered_username": username, "official_entity": entity}
                for number, username, entity in records
            ],
            "urls_checked": link_checks or [],
            "detected_handles": handles,
            "red_flags": _unique(flags),
        }

