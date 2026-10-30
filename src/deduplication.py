"""Deterministic deduplication and normalization engine for Wake Prospector."""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Set
from urllib.parse import urlparse

from src.config import ConfidenceLevel
from src.models import Lead


GENERIC_DOMAINS = {
    "instagram.com",
    "facebook.com",
    "fb.com",
    "linkedin.com",
    "google.com",
    "maps.google.com",
    "goo.gl",
    "wa.me",
    "api.whatsapp.com",
    "guiamais.com.br",
    "telelistas.net",
    "apontador.com.br",
    "linktr.ee",
    "beacons.ai",
}

LEGAL_SUFFIXES_REGEX = re.compile(
    r"\b(ltda|me|epp|eireli|s/?a|sociedade\s+anonima|s/?s|microempresa|limitada)\b",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """Removes diacritics, lowercase and removes extra punctuation and whitespace."""
    if not text:
        return ""
    # Remove accents
    nfkd = unicodedata.normalize("NFKD", text)
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Remove punctuation
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    # Lowercase and normalize whitespace
    return " ".join(cleaned.lower().split())


def normalize_business_name(name: str) -> str:
    """Normalizes business name by removing corporate legal designations and punctuation."""
    if not name:
        return ""
    normalized = normalize_text(name)
    cleaned = LEGAL_SUFFIXES_REGEX.sub(" ", normalized)
    return " ".join(cleaned.split())


def parse_br_phone(raw_phone: str) -> dict:
    """Parses a Brazilian phone number and accurately classifies mobile vs landline.

    - Mobile: 11 digits: DDD (2) + 9 + 8 digits (e.g. (21) 99921-7485).
    - Landline: 10 digits: DDD (2) + [2-5] + 7 digits (e.g. (21) 3353-5659).
    - Legacy Mobile: 10 digits starting with [6-9] after DDD (needs 9 prefix).
    """
    if not raw_phone:
        return {
            "type": "EMPTY",
            "normalized": "",
            "display": "",
            "is_mobile": False,
            "is_landline": False,
        }

    digits = re.sub(r"\D", "", raw_phone)
    if not digits:
        return {
            "type": "EMPTY",
            "normalized": "",
            "display": "",
            "is_mobile": False,
            "is_landline": False,
        }

    if digits.startswith("55") and len(digits) in (12, 13):
        national = digits[2:]
    else:
        national = digits

    if len(national) == 11 and national[2] == "9":
        ddd = national[:2]
        p1 = national[2:7]
        p2 = national[7:11]
        return {
            "type": "MOBILE",
            "normalized": "55" + national,
            "display": f"({ddd}) {p1}-{p2}",
            "is_mobile": True,
            "is_landline": False,
        }
    elif len(national) == 10:
        ddd = national[:2]
        sub_first = national[2]
        if sub_first in "2345":
            p1 = national[2:6]
            p2 = national[6:10]
            return {
                "type": "LANDLINE",
                "normalized": "55" + national,
                "display": f"({ddd}) {p1}-{p2}",
                "is_mobile": False,
                "is_landline": True,
            }
        else:
            full = ddd + "9" + national[2:]
            p1 = full[2:7]
            p2 = full[7:11]
            return {
                "type": "MOBILE",
                "normalized": "55" + full,
                "display": f"({ddd}) {p1}-{p2}",
                "is_mobile": True,
                "is_landline": False,
            }
    elif len(national) in (8, 9):
        # Missing area code, keep bare
        return {
            "type": "UNKNOWN",
            "normalized": digits,
            "display": raw_phone,
            "is_mobile": False,
            "is_landline": False,
        }

    return {
        "type": "UNKNOWN",
        "normalized": digits,
        "display": raw_phone,
        "is_mobile": False,
        "is_landline": False,
    }


def normalize_phone(raw_phone: str) -> str:
    """Normalizes phone numbers to standard numeric representation (defaulting to BR E.164).

    Examples:
    '(21) 98765-4321' -> '5521987654321'
    '+55 (21) 2620-1234' -> '552126201234'
    '21987654321' -> '5521987654321'
    """
    parsed = parse_br_phone(raw_phone)
    return parsed.get("normalized", "")


def format_display_phone(raw_phone: str) -> str:
    """Formats a phone number in standard Brazilian format: (XX) 9XXXX-XXXX or (XX) XXXX-XXXX."""
    parsed = parse_br_phone(raw_phone)
    return parsed.get("display", raw_phone)


def is_brazilian_mobile(raw_phone: str) -> bool:
    """Checks whether the phone is a confirmed mobile number."""
    return parse_br_phone(raw_phone).get("is_mobile", False)


def is_brazilian_landline(raw_phone: str) -> bool:
    """Checks whether the phone is a confirmed landline number."""
    return parse_br_phone(raw_phone).get("is_landline", False)


def extract_domain(url: str) -> str:
    """Extracts base domain from a URL, ignoring www, protocol, port and trailing paths."""
    if not url:
        return ""

    cleaned_url = url.strip()
    if not cleaned_url.startswith(("http://", "https://")):
        cleaned_url = "https://" + cleaned_url

    try:
        parsed = urlparse(cleaned_url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if ":" in domain:
            domain = domain.split(":")[0]
        return domain
    except Exception:
        return ""


def is_generic_domain(domain: str) -> bool:
    """Checks if the domain is a social network, directory, or aggregator."""
    if not domain:
        return True
    return any(domain == g or domain.endswith("." + g) for g in GENERIC_DOMAINS)


@dataclass
class DuplicateMatchResult:
    is_duplicate: bool = False
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    matched_lead_id: Optional[str] = None
    matched_criteria: List[str] = field(default_factory=list)
    reason: str = ""


def get_lead_normalized_phones(lead: Lead) -> Set[str]:
    """Collects all valid normalized phone numbers associated with a lead."""
    phones = set()
    for contact in lead.contacts:
        if contact.phone:
            norm = normalize_phone(contact.phone)
            if len(norm) >= 10:  # Minimum valid phone with area code
                phones.add(norm)
    return phones


def check_lead_duplicate(
    candidate: Lead,
    existing_leads: List[Lead],
) -> DuplicateMatchResult:
    """Checks whether a candidate Lead matches any existing Lead in the database.

    Evaluates:
    1. Normalized phone match (HIGH confidence)
    2. Non-generic domain match (HIGH confidence)
    3. Normalized Name + Normalized City match (HIGH confidence)
    4. Strong partial name match in the same city (MEDIUM confidence)
    """
    candidate_norm_name = normalize_business_name(candidate.business.name)
    candidate_norm_city = normalize_text(candidate.business.city)
    candidate_phones = get_lead_normalized_phones(candidate)
    candidate_domain = extract_domain(candidate.business.website)
    candidate_has_own_domain = (
        candidate_domain and not is_generic_domain(candidate_domain)
    )

    for existing in existing_leads:
        # Avoid self-comparison
        if existing.id == candidate.id:
            continue

        matched_criteria = []

        # 1. Phone match
        existing_phones = get_lead_normalized_phones(existing)
        common_phones = candidate_phones.intersection(existing_phones)
        if common_phones:
            matched_criteria.append(
                f"PHONE_MATCH ({', '.join(sorted(common_phones))})"
            )

        # 2. Domain match
        existing_domain = extract_domain(existing.business.website)
        if (
            candidate_has_own_domain
            and existing_domain
            and not is_generic_domain(existing_domain)
            and candidate_domain == existing_domain
        ):
            matched_criteria.append(f"DOMAIN_MATCH ({candidate_domain})")

        # 3. Exact Name + City match
        existing_norm_name = normalize_business_name(existing.business.name)
        existing_norm_city = normalize_text(existing.business.city)

        same_city = (
            candidate_norm_city
            and existing_norm_city
            and (candidate_norm_city == existing_norm_city)
        )

        exact_name_match = (
            candidate_norm_name
            and existing_norm_name
            and (candidate_norm_name == existing_norm_name)
        )

        if exact_name_match and same_city:
            matched_criteria.append("EXACT_NAME_AND_CITY_MATCH")

        # Decision based on criteria
        if matched_criteria:
            return DuplicateMatchResult(
                is_duplicate=True,
                confidence=ConfidenceLevel.HIGH,
                matched_lead_id=existing.id,
                matched_criteria=matched_criteria,
                reason=(
                    f"Candidate matches existing lead {existing.id} by: "
                    + "; ".join(matched_criteria)
                ),
            )

        # 4. Same city and substantial name similarity (word set overlap)
        if same_city and candidate_norm_name and existing_norm_name:
            words1 = set(candidate_norm_name.split())
            words2 = set(existing_norm_name.split())
            if words1 and words2:
                overlap = len(words1.intersection(words2))
                jaccard = overlap / len(words1.union(words2))
                # If high overlap (>= 0.75) and at least 2 common significant words
                if jaccard >= 0.75 or (
                    overlap >= 2 and (overlap == len(words1) or overlap == len(words2))
                ):
                    return DuplicateMatchResult(
                        is_duplicate=True,
                        confidence=ConfidenceLevel.MEDIUM,
                        matched_lead_id=existing.id,
                        matched_criteria=[
                            f"NAME_SIMILARITY ({candidate_norm_name} ~ {existing_norm_name})"
                        ],
                        reason=(
                            f"Potential duplicate of {existing.id} in {candidate.business.city} "
                            f"(high name similarity: '{candidate.business.name}' vs '{existing.business.name}')"
                        ),
                    )

    return DuplicateMatchResult(
        is_duplicate=False,
        confidence=ConfidenceLevel.HIGH,
        matched_lead_id=None,
        matched_criteria=[],
        reason="No duplicate match found.",
    )
