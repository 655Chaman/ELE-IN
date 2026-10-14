import re
import unicodedata
from urllib.parse import urlparse, urlunparse
from typing import Optional, Any


class DataHygieneService:
    @staticmethod
    def sanitize_text(text: Any, max_length: int = 500) -> str:
        """
        Paranoia Layer 1 & 2: Strips NUL bytes, unpaired surrogates, and control chars
        that cause database write crashes. Enforces max length.
        Paranoia Layer 0 & 2: Neutralizes formula injection triggers (CWE-1236).
        """
        if text is None:
            return ""
        s = str(text)
        s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s)
        s = s.encode('utf-8', 'ignore').decode('utf-8', 'ignore')

        raw_str = str(text).lstrip(' ')
        s = s[:max_length].strip()
        if not s:
            return ""

        formula_triggers = ('=', '+', '-', '@', '\t', '\r')
        if s.startswith(formula_triggers) or raw_str.startswith(formula_triggers):
            # Preserves legitimate signed numbers like -42 or +3.14
            is_signed_number = False
            if s.startswith(('+', '-')) and not raw_str.startswith(('=', '@', '\t', '\r')):
                if re.match(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$', s):
                    is_signed_number = True
            if not is_signed_number and not s.startswith("'"):
                s = "'" + s
        return s

    @staticmethod
    def sanitize_csv_cell(cell: Any) -> str:
        """
        Dedicated helper returning string with formula injection protection (CWE-1236).
        """
        return DataHygieneService.sanitize_text(cell)

    @staticmethod
    def sanitize_for_csv(cell: Any) -> str:
        """
        Alias for sanitize_csv_cell returning string with formula injection protection (CWE-1236).
        """
        return DataHygieneService.sanitize_text(cell)

    @staticmethod
    def clean_name(name: Any) -> str:
        """
        Cleans personal names across Three Paranoia Layers:
        - Layer 0: Strips titles, emojis, fixes casing.
        - Layer 1: Type safety for non-string inputs; preserves apostrophes (O'Connor, D'Angelo) 
                   and accents (René, Müller); handles Unicode normalization.
        - Layer 2: If sanitization strips all characters (e.g. name was literally a title like 'Dr.'), 
                   gracefully falls back to the original trimmed text.
        """
        if name is None:
            return ""
        raw_str = str(name).strip()
        if not raw_str:
            return ""

        # Normalize unicode (e.g. composed vs decomposed accents)
        norm = unicodedata.normalize("NFKC", raw_str)

        # Replace underscores with spaces (common in filenames/exports)
        norm = norm.replace("_", " ")

        # Keep letters (including accented), spaces, hyphens, and apostrophes
        cleaned = re.sub(r"[^\w\s\-\']", "", norm, flags=re.UNICODE)

        # Remove common formal titles/prefixes and suffixes
        titles = r"\b(mr|mrs|ms|miss|dr|prof|phd|md|mba|cpa|jr|sr|ii|iii|iv)\b\.?"
        without_titles = re.sub(titles, "", cleaned, flags=re.IGNORECASE)

        # Collapse whitespace
        without_titles = re.sub(r"\s+", " ", without_titles).strip()

        # If title removal emptied the name, fallback to cleaned
        final_candidate = without_titles if without_titles else cleaned.strip()
        if not final_candidate:
            return raw_str

        # Fix capitalization if ALL CAPS or all lower
        if final_candidate.isupper() or final_candidate.islower():
            final_candidate = final_candidate.title()

        return final_candidate.strip()

    @staticmethod
    def clean_company(company: Any) -> str:
        """
        Cleans company names across Three Paranoia Layers:
        - Layer 0: Strips legal entity suffixes (LLC, Inc, Corp, etc.), fixes casing.
        - Layer 1: Type safety; preserves ampersands (&) and hyphens (-); protects standalone 
                   brand names from being completely wiped.
        - Layer 2: If stripping legal entities leaves the string empty (e.g. company was 'LLC' or 'The Co'), 
                   falls back to the original trimmed company name.
        """
        if company is None:
            return ""
        raw_str = str(company).strip()
        if not raw_str:
            return ""

        norm = unicodedata.normalize("NFKC", raw_str)
        norm = norm.replace("_", " ")

        # Remove legal entities at word boundaries (case-insensitive)
        entities = r"\b(llc|inc|corp|corporation|gmbh|ltd|limited|pvt|pty|sa|sarl|bv|plc|ag|co)\b\.?"
        without_entities = re.sub(entities, "", norm, flags=re.IGNORECASE)

        # Remove emojis and unexpected punctuation (keep alphanumeric, space, hyphens, &, apostrophes)
        cleaned = re.sub(r"[^\w\s\-\&\']", "", without_entities, flags=re.UNICODE)

        # Clean extra spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Clean trailing hyphens, commas, ampersands
        cleaned = re.sub(r"[\-\,\&]+$", "", cleaned).strip()

        # Fallback if stripping stripped everything or left only standalone articles ('The', 'A')
        if not cleaned or cleaned.lower() in ["the", "a", "an"] or len(cleaned) < 2:
            return re.sub(r"\s+", " ", raw_str).strip()

        # Fix ALL CAPS for non-acronyms (preserve short acronyms like AT&T, IBM, SAP <= 4 letters)
        if cleaned.isupper():
            letters_only = re.findall(r"[A-Za-z]", cleaned)
            if len(letters_only) > 4:
                cleaned = cleaned.title()

        return cleaned.strip()

    @staticmethod
    def is_search_url(url: Any) -> bool:
        """
        Detects whether a URL is a LinkedIn search query or Sales Navigator search URL
        rather than an individual personal profile.
        """
        if not url:
            return False
        raw = str(url).lower()
        search_markers = [
            "linkedin.com/sales/search",
            "linkedin.com/search/results",
            "linkedin.com/sales/lead/search",
            "/search/results/people",
            "origin=faceted_search",
            "origin=switch_search_vertical"
        ]
        return any(marker in raw for marker in search_markers)

    @staticmethod
    def is_profile_url(url: Any) -> bool:
        """
        Checks whether a URL points to an individual LinkedIn profile.
        """
        if not url or DataHygieneService.is_search_url(url):
            return False
        raw = str(url).lower()
        return bool(
            re.search(r"linkedin\.com/(in|pub|sales/lead|sales/people)/[a-zA-Z0-9_\-]+", raw)
        )

    @staticmethod
    def clean_linkedin_url(url: Any) -> str:
        """Alias for normalize_linkedin_url."""
        return DataHygieneService.normalize_linkedin_url(url)

    @staticmethod
    def normalize_linkedin_url(url: Any) -> str:
        """
        Normalizes LinkedIn profile URLs across Three Paranoia Layers:
        - Layer 0: Ensures scheme, standard domain, and path.
        - Layer 1: Normalizes subdomains (in.linkedin.com, uk.linkedin.com -> www.linkedin.com),
                   strips query parameters (?miniProfileUrn=..., ?trk=..., ?utm=...),
                   strips trailing slashes and URL fragments (#experience),
                   canonicalizes '/in/Username' path to lowercase for deterministic deduplication,
                   safely handles missing 'https://' prefix.
        - Layer 2: Strips enclosing quotes, angle brackets <>, parentheses, markdown artifacts,
                   strictly rejects search queries (/sales/search, /search/results) and non-profile 
                   pages (/company, /jobs, /feed) to prevent corrupting lead databases with invalid 
                   dummy profiles, and returns empty string '' for invalid non-LinkedIn domains.
        """
        if not url:
            return ""
        raw = str(url).strip()
        # Strip enclosing wrappers from markdown, lists, or quotes
        for _ in range(3):
            raw = raw.strip()
            if len(raw) >= 2:
                if (raw.startswith("<") and raw.endswith(">")) or \
                   (raw.startswith('"') and raw.endswith('"')) or \
                   (raw.startswith("'") and raw.endswith("'")) or \
                   (raw.startswith("[") and raw.endswith("]")) or \
                   (raw.startswith("(") and raw.endswith(")")):
                    raw = raw[1:-1].strip()
        if not raw:
            return ""

        # Layer 2: Reject search URLs immediately — searches are NOT profile leads
        if DataHygieneService.is_search_url(raw):
            return ""

        # Prepend https if missing
        if not raw.startswith("http://") and not raw.startswith("https://"):
            raw = "https://" + raw

        try:
            parsed = urlparse(raw)
            netloc = parsed.netloc.lower()
            if "linkedin.com" not in netloc:
                return ""

            # Canonical netloc
            std_netloc = "www.linkedin.com"

            # Clean path
            path = parsed.path.rstrip("/")
            parts = path.split("/")

            # Reject non-profile paths (company, school, jobs, feed, learning, pulse, groups)
            if len(parts) >= 2:
                section = parts[1].lower()
                if section in ("company", "school", "jobs", "feed", "learning", "pulse", "groups"):
                    return ""

            # Canonicalize /in/username profile paths
            if len(parts) >= 3 and parts[1].lower() == "in":
                vanity = parts[2].strip(".-,")
                vanity = vanity.lower()
                dummy_usernames = {
                    "null", "undefined", "unknown", "linkedin", "profile", 
                    "me", "feed", "jobs", "company", "view", "edit"
                }
                if not vanity or vanity in dummy_usernames:
                    return ""
                path = f"/in/{vanity}"

            # Canonicalize Sales Navigator URLs (/sales/lead/... or /sales/people/...)
            elif len(parts) >= 4 and parts[1].lower() == "sales" and parts[2].lower() in ("lead", "people"):
                sales_type = parts[2].lower()
                identifier_raw = parts[3].strip(".-,")
                # Isolate clean identifier if comma-separated (e.g. ACwAABBCC,NAME,xyz)
                clean_id = identifier_raw.split(",")[0].strip()
                if not clean_id:
                    return ""
                path = f"/sales/{sales_type}/{clean_id}"

            # Rebuild clean URL without query parameters or fragments
            return urlunparse(("https", std_netloc, path, "", "", ""))
        except Exception:
            return ""

    @staticmethod
    def clean_email(email: Any) -> str:
        """
        Cleans and validates email addresses across Three Paranoia Layers:
        - Layer 0: Strips whitespace, mailto: prefix, angle brackets (<user@domain.com>), quotes, lowercases.
        - Layer 1: Validates format against strict RFC regex (standard user@domain.tld). Rejects invalid formats.
        - Layer 2: Sanitizes injection patterns, rejects non-string types, strips NUL bytes/control chars,
                   and rejects dummy/catch-all garbage emails.
        """
        if email is None:
            return ""
        raw = str(email).strip()
        if not raw:
            return ""

        # Layer 0 & 2: Strip wrappers: quotes, angle brackets, mailto:
        raw = re.sub(r'[\x00-\x1f\x7f]', '', raw)
        for _ in range(4):
            raw = raw.strip()
            if raw.lower().startswith("mailto:"):
                raw = raw[7:].strip()
            if (raw.startswith("<") and raw.endswith(">")) or \
               (raw.startswith('"') and raw.endswith('"')) or \
               (raw.startswith("'") and raw.endswith("'")) or \
               (raw.startswith("[") and raw.endswith("]")):
                raw = raw[1:-1].strip()
        if raw.lower().startswith("mailto:"):
            raw = raw[7:].strip()

        raw = raw.lower()

        # Reject explicit dummy/catch-all garbage email prefixes/domains
        dummy_prefixes = ("none@", "test@", "null@", "undefined@", "fake@", "no-reply@", "noreply@")
        dummy_suffixes = ("@test.com", "@domain.com")
        if raw.startswith(dummy_prefixes) or raw.endswith(dummy_suffixes):
            return ""

        # Layer 1 Paranoia: RFC regex validation
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(email_regex, raw):
            return ""

        # Must have valid domain parts (no consecutive dots or trailing dot)
        parts = raw.split("@", 1)
        if len(parts) != 2:
            return ""
        domain = parts[1]
        if ".." in domain or domain.startswith(".") or domain.endswith("."):
            return ""

        return raw

    @staticmethod
    def clean_phone(phone: Any) -> str:
        """
        Cleans and normalizes phone numbers across Three Paranoia Layers:
        - Layer 0: Strips whitespace, hyphens, parentheses, periods, and extension markers.
        - Layer 1: Preserves leading '+' for international E.164 numbers; extracts digits.
        - Layer 2: Validates digit length (minimum 7 digits, maximum 16 digits). Rejects garbage strings.
        """
        if phone is None:
            return ""
        raw = str(phone).strip()
        if not raw:
            return ""

        # Strip extensions like ext. 123, x456, extension 789, x 101
        raw = re.split(r'(?:\bext\.?|\bextension\.?|\bx)\s*\d+', raw, flags=re.IGNORECASE)[0].strip()

        has_plus = raw.startswith("+")
        digits = re.sub(r'\D', '', raw)

        # A valid phone number has between 7 and 16 digits
        if len(digits) < 7 or len(digits) > 16:
            return ""

        return f"+{digits}" if has_plus else digits


    @staticmethod
    def deduplicate_leads(leads: list, match_field: str = "auto") -> list:
        """
        Deduplicates a list of lead dictionaries across Three Paranoia Layers:
        - Layer 0: Matches by canonical LinkedIn URL, fallback to clean email.
        - Layer 1: Merges metadata (preserves non-empty fields when a duplicate provides richer data).
        - Layer 2: Safely handles non-dict elements, preserves ordering of first occurrence.
        """
        if not leads or not isinstance(leads, list):
            return []

        seen_keys = {}
        unique_leads = []

        for lead in leads:
            if not isinstance(lead, dict):
                continue

            # Determine deduplication key
            raw_url = lead.get("linkedin_url") or lead.get("url") or lead.get("profile_url")
            norm_url = DataHygieneService.normalize_linkedin_url(raw_url) if raw_url else ""

            raw_email = lead.get("email")
            norm_email = DataHygieneService.clean_email(raw_email) if raw_email else ""

            dedupe_key = None
            if match_field == "linkedin_url":
                dedupe_key = norm_url or None
            elif match_field == "email":
                dedupe_key = norm_email or None
            else:  # auto
                dedupe_key = norm_url or norm_email or None

            # If no unique identifier exists, keep lead as unique
            if not dedupe_key:
                clean_lead = dict(lead)
                if norm_url:
                    clean_lead["linkedin_url"] = norm_url
                if norm_email:
                    clean_lead["email"] = norm_email
                unique_leads.append(clean_lead)
                continue

            if dedupe_key in seen_keys:
                # Merge richer data into existing lead
                existing = seen_keys[dedupe_key]
                for k, v in lead.items():
                    if v and not existing.get(k):
                        existing[k] = v
            else:
                clean_lead = dict(lead)
                if norm_url:
                    clean_lead["linkedin_url"] = norm_url
                if norm_email:
                    clean_lead["email"] = norm_email
                seen_keys[dedupe_key] = clean_lead
                unique_leads.append(clean_lead)

        return unique_leads

    @staticmethod
    def split_full_name(name_str: Optional[str]) -> tuple:
        """
        Paranoia Layer 0 & 2: Safely splits a single full name string into (first_name, last_name).
        - Strips titles, honorifics (Dr., Mr., Mrs., Ms., Prof., Rev.)
        - Strips professional/generational suffixes (Ph.D., MD, Jr., Sr., III, Esq., CPA)
        - Returns (first_name, last_name) tuple with clean title-casing.
        """
        if not name_str:
            return ("", "")
        from leads.backend.services.lead_ingestion_service import split_full_name
        return split_full_name(name_str)
