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
    def _format_name_casing(s: str) -> str:
        """
        Converts ALL-CAPS ('SARAH') or all-lowercase ('sarah') to title case ('Sarah'),
        while preserving mixed-case or capitalized particles ('McCall', 'O'Connor', 'van der Merwe', 'de Silva').
        """
        if s.isupper() or s.islower():
            words = s.split()
            particles = {"van", "der", "de", "del", "da", "di", "von", "la", "le", "du"}
            new_words = []
            for i, w in enumerate(words):
                if i > 0 and w.lower() in particles:
                    new_words.append(w.lower())
                else:
                    w_title = w.title()
                    w_title = re.sub(r"\bMc([a-z])", lambda m: f"Mc{m.group(1).upper()}", w_title)
                    new_words.append(w_title)
            return " ".join(new_words)
        return s

    @staticmethod
    def clean_name(name: Any) -> str:
        """
        Cleans personal names across Three Paranoia Layers:
        - Layer 0: Strips titles, emojis, bracketed status tags, attached job titles after separators, fixes casing.
        - Layer 1: Type safety for non-string inputs; preserves apostrophes (O'Connor, D'Angelo),
                   hyphens (Mary-Jane), and accents (René, Müller); handles Unicode normalization.
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

        # Strip parenthetical, bracketed, or curly-brace tags: (We're hiring), (she/her), [Hiring AEs], {Open to work}
        norm = re.sub(r"\s*[\(\[\{].*?[\)\]\}]", "", norm)
        norm = re.sub(r"\s*[\(\[\{][^\)\]\}]*$", "", norm)

        # Strip attached job titles and status announcements after separators ( - , | , • , / , – , — )
        norm = re.split(r"\s+[-–—•/]\s*|\s*[-–—•/]\s+|\s*\|\s*", norm)[0].strip()

        # Replace underscores with spaces (common in filenames/exports)
        norm = norm.replace("_", " ")

        # Keep letters (including accented), spaces, hyphens, and apostrophes (strips emojis and decorative symbols)
        cleaned = re.sub(r"[^\w\s\-\']", "", norm, flags=re.UNICODE)

        # Remove common formal titles/prefixes and suffixes: \b(mr|mrs|ms|miss|dr|prof|phd|md|mba|cpa|pmp|esq|jr|sr|ii|iii|iv)\b\.?
        titles = r"\b(mr|mrs|ms|miss|dr|prof|phd|md|mba|cpa|pmp|esq|jr|sr|ii|iii|iv)\b\.?"
        without_titles = re.sub(titles, "", cleaned, flags=re.IGNORECASE)

        # Collapse whitespace
        without_titles = re.sub(r"\s+", " ", without_titles).strip()

        # If title removal emptied the name, fallback to raw_str
        final_candidate = without_titles if without_titles else raw_str
        if not final_candidate:
            return DataHygieneService.sanitize_text(raw_str)

        # Format casing
        final_candidate = DataHygieneService._format_name_casing(final_candidate)

        # Paranoia Layer 1 & 2 (B1-F09): Strip leading/trailing single/double quotes and hyphens so CSV escaping does not leak into names
        final_candidate = final_candidate.strip().strip("'\"-").strip()
        if final_candidate.startswith(('=', '@', '\t', '\r')):
            final_candidate = "'" + final_candidate

        return final_candidate

    @staticmethod
    def clean_first_name(name: Any) -> str:
        """
        Extracts a clean, single first-name token across Three Paranoia Layers:
        - Layer 0: Takes raw full name or first name, applies clean_name, extracts single first name token.
        - Layer 1: Handles initials: if first token is a single letter or initial like 'J.'
                   in 'J. Robert Oppenheimer', picks 'Robert'.
                   Strips any trailing punctuation.
        - Layer 2: Gracefully falls back if all tokens are single letters or string cannot be parsed.
        """
        if name is None:
            return ""
        raw_str = str(name).strip()
        cleaned = DataHygieneService.clean_name(name)
        if not cleaned:
            return ""
        if cleaned == raw_str and len(cleaned.split()) <= 1:
            return cleaned

        tokens = cleaned.split()
        if not tokens:
            return ""

        first_token = ""
        for idx, t in enumerate(tokens):
            t_clean = re.sub(r"^[\W_]+|[\W_]+$", "", t)
            # If t_clean is single letter (initial) and there are subsequent tokens, advance
            if len(t_clean) <= 1 and (idx + 1) < len(tokens):
                continue
            first_token = t_clean
            break

        if not first_token and tokens:
            first_token = re.sub(r"^[\W_]+|[\W_]+$", "", tokens[0])

        return first_token.rstrip(".,;:-_/'\"").strip()

    @staticmethod
    def clean_company(company: Any) -> str:
        """
        Cleans company names across Three Paranoia Layers:
        - Layer 0: Strips parenthetical tags, marketing taglines/slogans after delimiters,
                   legal entity suffixes, fixes casing.
        - Layer 1: Detects and strips domain imports ('tryacme.io' -> 'Acme', 'getscale.ai' -> 'Scale'),
                   stripping leading 'try', 'get', 'use' if followed by word.
                   Preserves short legitimate acronyms ('IBM', 'AWS', 'SAP', 'BMW', 'HP', 'GMC').
                   Fixes ALL CAPS for names > 4 letters ('APPLE, INC.' -> 'Apple').
        - Layer 2: If stripping leaves empty string or single letter, falls back to original trimmed company string.
        """
        if company is None:
            return ""
        raw_str = str(company).strip()
        if not raw_str:
            return ""

        norm = unicodedata.normalize("NFKC", raw_str)

        # Strip parenthetical, bracketed, or curly-brace tags: (YC W19), (formerly Twitter), (acquired by Google)
        norm = re.sub(r"\s*[\(\[\{].*?[\)\]\}]", "", norm)
        norm = re.sub(r"\s*[\(\[\{][^\)\]\}]*$", "", norm)

        # Strip marketing taglines, slogans, and value propositions after delimiters ( - , | , : , • , – , — )
        norm = re.split(r"\s+[-–—•:]\s*|\s*[-–—•:]\s+|\s*\|\s*", norm)[0].strip()

        # Check if company was imported as a domain/URL (e.g. tryacme.io, getscale.ai, www.acme.co)
        dom_match = re.match(
            r"^(?:https?://)?(?:www\.)?([a-zA-Z0-9][a-zA-Z0-9-_]*)\.(?:[a-zA-Z]{2,10}(?:\.[a-zA-Z]{2,4})?)(?:/.*)?$",
            norm.strip(),
            flags=re.IGNORECASE
        )
        if dom_match:
            base_name = dom_match.group(1)
            # Strip leading "try", "get", "use" if followed by a word (>= 2 letters)
            base_name = re.sub(r"^(?:try|get|use)[-_]?(?=[a-zA-Z]{2,})", "", base_name, flags=re.IGNORECASE)
            norm = base_name

        norm = norm.replace("_", " ")

        # Remove legal entity suffixes: LLC, Inc, Corp, GmbH, Ltd, Pty Ltd, Pvt Ltd, SA, BV, PLC, Co, Company
        entities = r"(?:\b(l\.l\.c\.|llc|incorporated|inc|corporation|corp|gmbh|limited|ltd|pvt|pty|s\.a\.|sa|sarl|b\.v\.|bv|plc|ag|company|co)\b\.?|\bl\.l\.c\.?|\bb\.v\.?|\bs\.a\.?)"
        without_entities = re.sub(entities, "", norm, flags=re.IGNORECASE)

        # Remove emojis and unexpected punctuation (keep alphanumeric, space, hyphens, &, apostrophes)
        cleaned = re.sub(r"[^\w\s\-\&\']", "", without_entities, flags=re.UNICODE)

        # Clean extra spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Clean trailing hyphens, commas, ampersands
        cleaned = re.sub(r"[\-\,\&]+$", "", cleaned).strip()

        # Strip leading "The " if followed by brand name (e.g. "The Coca-Cola Company" -> "Coca-Cola")
        if re.match(r"^the\s+\S+", cleaned, flags=re.IGNORECASE) and cleaned.lower() not in ["the co", "the company", "the inc", "the llc"]:
            cleaned = re.sub(r"^the\s+", "", cleaned, flags=re.IGNORECASE).strip()

        # Fallback: If stripping leaves empty string or single letter (except 'X'), fallback to original trimmed company string
        if not cleaned or (len(cleaned) <= 1 and cleaned.upper() != "X") or cleaned.lower() in ["the", "a", "an"]:
            fallback = re.sub(r"\s+", " ", raw_str).strip().strip("'\"-").strip()
            if fallback.startswith(('=', '@', '\t', '\r')):
                fallback = "'" + fallback
            return fallback

        # Fix ALL CAPS for names > 4 letters (e.g. "APPLE, INC." -> "Apple"), while preserving short legitimate acronyms ("IBM", "AWS", "SAP", "BMW", "HP", "GMC")
        if cleaned.isupper():
            letters_only = re.findall(r"[A-Za-z]", cleaned)
            if len(letters_only) > 4:
                cleaned = cleaned.title()

        # Fix all-lowercase
        elif cleaned.islower():
            if cleaned.lower() in {"ibm", "aws", "sap", "bmw", "hp", "gmc", "att", "gmac"}:
                cleaned = cleaned.upper()
            else:
                cleaned = cleaned.title()

        # Paranoia Layer 1 & 2 (B1-F09): Strip leading/trailing quotes and hyphens so CSV escaping does not leak into company tokens
        final_company = cleaned.strip().strip("'\"-").strip()
        if final_company.startswith(('=', '@', '\t', '\r')):
            final_company = "'" + final_company
        return final_company

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
        # Paranoia Layer 1: Bound input length to 2048 chars to prevent ReDoS on dirty inputs
        if len(raw) > 2048:
            return ""
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
        # Paranoia Layer 1: Bound input length to 320 chars (RFC 5321 limit) to prevent ReDoS
        if not raw or len(raw) > 320:
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

        # Validate TLD: must have at least 2 characters, alpha or valid punycode (e.g. .technology, .consulting, .ai, .co.uk)
        domain_labels = domain.split(".")
        if len(domain_labels) < 2:
            return ""
        tld = domain_labels[-1]
        if len(tld) < 2 or not re.match(r'^(?:[a-zA-Z]{2,}|xn--[a-zA-Z0-9]+)$', tld):
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
        # Paranoia Layer 1: Bound input length to 50 chars to prevent ReDoS
        if not raw or len(raw) > 50:
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
