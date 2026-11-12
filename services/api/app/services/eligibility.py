from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.db.models.enums import EligibilityStatus
from app.schemas.collector import NormalizedCandidate
from app.services.text import normalize_whitespace

INDIA_PATTERNS = [
    r"\bindia\b",
    r"\bbengaluru\b",
    r"\bbangalore\b",
    r"\bmumbai\b",
    r"\bnew delhi\b",
    r"\bdelhi\b",
    r"\bhyderabad\b",
    r"\bpune\b",
    r"\bchennai\b",
    r"\bgurugram\b",
    r"\bgurgaon\b",
    r"\bnoida\b",
    r"\bkolkata\b",
    r"\bahmedabad\b",
    r"\bjaipur\b",
    r"\bkochi\b",
    r"\bkerala\b",
    r"\bkarnataka\b",
    r"\btamil nadu\b",
    r"\btelangana\b",
    r"\bandhra pradesh\b",
    r"\bmaharashtra\b",
    r"\bgujarat\b",
    r"\brajasthan\b",
    r"\buttar pradesh\b",
    r"\bharyana\b",
    r"\bwest bengal\b",
    r"\bodisha\b",
    r"\bmadhya pradesh\b",
    r"\bchhattisgarh\b",
    r"\bbihar\b",
    r"\bgoa\b",
    r"\bremote\s*[-–(]\s*india\b",
    r"\bindia\s*[-–)]\s*remote\b",
]

NON_INDIA_COUNTRY_NAMES = {
    "united states": "US",
    "usa": "US",
    "u.s.": "US",
    "canada": "CA",
    "united kingdom": "GB",
    "uk": "GB",
    "germany": "DE",
    "france": "FR",
    "netherlands": "NL",
    "ireland": "IE",
    "spain": "ES",
    "poland": "PL",
    "portugal": "PT",
    "switzerland": "CH",
    "sweden": "SE",
    "denmark": "DK",
    "norway": "NO",
    "finland": "FI",
    "australia": "AU",
    "new zealand": "NZ",
    "singapore": "SG",
    "japan": "JP",
    "south korea": "KR",
    "china": "CN",
    "brazil": "BR",
    "mexico": "MX",
    "israel": "IL",
    "uae": "AE",
    "united arab emirates": "AE",
    "south africa": "ZA",
}

STUDENT_ONLY_PATTERNS = [
    r"\bstudent[s]?\s+only\b",
    r"\bonly\s+(?:open\s+)?(?:to\s+)?(?:current\s+)?students\b",
    r"\bopen\s+only\s+to\s+(?:current\s+)?students\b",
    r"\bmust\s+(?:currently\s+)?be\s+(?:an?\s+)?(?:currently\s+)?enrolled\s+student\b",
    r"\bcurrently\s+enrolled\s+(?:in|at)\b",
    r"\bmust\s+be\s+enrolled\s+(?:in|at)\b",
    r"\benrolled\s+students?\s+only\b",
    r"\bfinal[- ]year\s+students?\b",
    r"\bundergraduate\s+students?\s+only\b",
    r"\bfor\s+(?:current\s+)?(?:undergraduate|graduate)\s+students\s+only\b",
    r"\b2027\s+(?:batch|graduates?)\s+only\b",
    r"\bgraduating\s+in\s+2027\b",
    r"\bmust\s+graduate\s+in\s+2027\b",
    r"\bonly\s+(?:those\s+)?graduating\s+in\s+2027\b",
]

PROFESSIONAL_YES_PATTERNS = [
    r"\bworking\s+professionals?\b",
    r"\bopen\s+to\s+(?:working\s+)?professionals?\b",
    r"\bprofessionals?\s+(?:are\s+)?(?:welcome|eligible|encouraged)\b",
    r"\bfor\s+(?:working\s+)?professionals?\b",
    r"\bnon[- ]students?\b",
    r"\bnot\s+required\s+to\s+be\s+(?:a\s+)?student\b",
    r"\bneed\s+not\s+be\s+(?:a\s+)?student\b",
    r"\bno\s+student\s+status\s+required\b",
    r"\banyone\s+(?:can\s+apply|is\s+welcome)\b",
    r"\bstudent\s+status\s+(?:is\s+)?not\s+required\b",
    r"\b\d{1,2}\s*(?:\+|-|–|—|to)\s*\d{0,2}\s*\+?\s*years?\s+(?:of|in)\s+"
    r"professional\s+(?:software\s+)?(?:development|engineering)\s+experience\b",
    r"\b\d{1,2}\s*(?:\+|-|–|—|to)\s*\d{0,2}\s*\+?\s*years?\s+(?:of|in)\s+"
    r"(?:production|industry)(?:\s+(?:experience|code|software|engineering))?\b",
]

STUDENT_EXCEPTION_PATTERNS = [
    r"\bstudents?\s+(?:and|or)\s+(?:working\s+)?professionals?\b",
    r"\bprofessionals?\s+(?:and|or)\s+students?\b",
]

RECENT_GRADUATE_EXCEPTION_PATTERNS = [
    r"\bcompleted\s+(?:their|your|the)?\s*(?:latest\s+)?degree\s+in\s+\d{4}\b",
    r"\bgraduated\s+(?:in|between)\s+\d{4}\b",
    r"\bdegree\s+(?:completed|awarded)\s+in\s+\d{4}\b",
]

INDIA_ELIGIBILITY_PATTERNS = [
    r"\bindian\s+citizens?\b",
    r"\bcitizens?\s+of\s+india\b",
    r"\bresidents?\s+of\s+india\b",
    r"\bmust\s+(?:be\s+)?(?:currently\s+)?(?:based|residing|located)\s+in\s+india\b",
]

REMOTE_WORLDWIDE_PATTERNS = [
    r"\bworldwide\b",
    r"\bworld[- ]wide\b",
    r"\banywhere\b",
    r"\bglobal(?:ly)?\b",
    r"\binternational\b",
]

COUNTRY_CODE_PATTERN = re.compile(r"\b([A-Z]{2})\b")


@dataclass
class EligibilityResult:
    professional_eligibility: EligibilityStatus
    india_eligibility: EligibilityStatus
    student_only: bool
    student_eligibility: EligibilityStatus
    reasons: dict[str, str] = field(default_factory=dict)
    student_only_hit: str | None = None
    professional_hit: str | None = None
    india_hit: str | None = None


def corpus_for(candidate: NormalizedCandidate) -> str:
    pieces = [
        candidate.title,
        candidate.description_summary,
        candidate.requirements_summary,
        candidate.scope,
        candidate.location_text,
        candidate.employment_type,
    ]
    return normalize_whitespace(" ".join(piece for piece in pieces if piece)).lower()


def _matches(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def _has_exception(text: str) -> bool:
    return any(
        re.search(pattern, text, flags=re.IGNORECASE) for pattern in STUDENT_EXCEPTION_PATTERNS
    )


def infer_country_codes(candidate: NormalizedCandidate) -> list[str]:
    codes = {code.upper() for code in candidate.country_codes if len(code) == 2}
    text = normalize_whitespace(candidate.location_text or "").lower()
    if any(re.search(pattern, text) for pattern in INDIA_PATTERNS):
        codes.add("IN")
    for name, code in NON_INDIA_COUNTRY_NAMES.items():
        if name in text:
            codes.add(code)
    for code in COUNTRY_CODE_PATTERN.findall(candidate.location_text or ""):
        if code in {"IN", "US", "GB", "CA", "DE", "FR", "NL", "IE", "AU", "SG", "JP", "AE"}:
            codes.add(code)
    codes.discard("")
    return sorted(codes)


def infer_remote_countries(candidate: NormalizedCandidate) -> list[str]:
    if candidate.allowed_remote_countries:
        return sorted(
            {code.upper() for code in candidate.allowed_remote_countries if len(code) == 2}
        )
    text = normalize_whitespace(candidate.location_text or "").lower()
    codes: set[str] = set()
    for name, code in NON_INDIA_COUNTRY_NAMES.items():
        if re.search(rf"\bremote\b[^.;]{{0,60}}\b{re.escape(name)}\b", text):
            codes.add(code)
    if re.search(r"\bremote\b[^.;]{0,60}\bindia\b", text) or "remote india" in text:
        codes.add("IN")
    for code in COUNTRY_CODE_PATTERN.findall(candidate.location_text or ""):
        if re.search(rf"\bremote\b[^.;]{{0,60}}\b{code}\b", text):
            codes.add(code)
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in REMOTE_WORLDWIDE_PATTERNS):
        codes.add("IN")
    return sorted(codes)


def assess_eligibility(
    candidate: NormalizedCandidate, relocation_allowed: bool = False
) -> EligibilityResult:
    text = corpus_for(candidate)
    reasons: dict[str, str] = {}

    professional_yes_hit = _matches(PROFESSIONAL_YES_PATTERNS, text)
    recent_graduate_exception = _matches(RECENT_GRADUATE_EXCEPTION_PATTERNS, text)
    student_only_hit = _matches(STUDENT_ONLY_PATTERNS, text)
    if student_only_hit and (
        (_has_exception(text) and professional_yes_hit) or recent_graduate_exception
    ):
        student_only_hit = None

    if student_only_hit:
        professional = EligibilityStatus.verified_no
        student_only = True
        student_eligibility = EligibilityStatus.verified_yes
        reasons["professional"] = (
            f'Explicit student-only/graduation restriction: "{student_only_hit}"'
        )
        reasons["student"] = f'Student-only text found: "{student_only_hit}"'
    elif professional_yes_hit:
        professional = EligibilityStatus.verified_yes
        student_only = False
        student_eligibility = EligibilityStatus.unknown
        reasons["professional"] = f'Explicit professional eligibility: "{professional_yes_hit}"'
        reasons["student"] = (
            "No student-only restriction found; professional eligibility is explicit"
        )
    else:
        professional = EligibilityStatus.unknown
        student_only = False
        student_eligibility = EligibilityStatus.unknown
        if recent_graduate_exception:
            reasons["professional"] = (
                "Graduation-year window includes recent graduates as well as current "
                "students; eligibility is not student-only"
            )
            reasons["student"] = (
                "Graduation-year window is broader than current students; student-only "
                "status remains unknown"
            )
        else:
            reasons["professional"] = (
                "No explicit statement that working professionals are eligible; absence of a "
                "student restriction is not positive evidence"
            )
            reasons["student"] = (
                "No explicit student-only restriction found; status remains unknown"
            )

    country_codes = infer_country_codes(candidate)
    remote_countries = infer_remote_countries(candidate)
    location_text = normalize_whitespace(candidate.location_text or "").lower()
    remote = candidate.is_remote or "remote" in location_text
    india_eligibility_hit = _matches(INDIA_ELIGIBILITY_PATTERNS, text)

    if "IN" in country_codes:
        india = EligibilityStatus.verified_yes
        india_hit = "Location/eligibility text names India"
    elif india_eligibility_hit:
        india = EligibilityStatus.verified_yes
        india_hit = f'Explicit India eligibility: "{india_eligibility_hit}"'
    elif remote:
        if "IN" in remote_countries:
            india = EligibilityStatus.verified_yes
            india_hit = "Remote role explicitly allows India/worldwide"
        elif remote_countries:
            india = EligibilityStatus.verified_no
            india_hit = "Remote role's published country list excludes India"
        else:
            india = EligibilityStatus.unknown
            india_hit = (
                "Remote flag is true but no India country allowlist was published; "
                "remote alone does not prove India eligibility"
            )
    elif country_codes:
        india = EligibilityStatus.verified_no
        india_hit = "Role country list excludes India and it is not remote"
    elif "remote" in location_text:
        india = EligibilityStatus.unknown
        india_hit = "Location mentions remote but does not name allowed countries"
    else:
        india = EligibilityStatus.unknown
        india_hit = "No explicit India location or country allowlist in the source evidence"

    if (
        india == EligibilityStatus.verified_no
        and candidate.requires_relocation
        and relocation_allowed
    ):
        reasons["location"] = (
            india_hit + "; relocation is opted in for research, not India eligibility"
        )
    else:
        reasons["location"] = india_hit

    return EligibilityResult(
        professional_eligibility=professional,
        india_eligibility=india,
        student_only=student_only,
        student_eligibility=student_eligibility,
        reasons=reasons,
        student_only_hit=student_only_hit,
        professional_hit=professional_yes_hit,
        india_hit=india_hit,
    )
