"""
Stage 21 Test Suite: Location & Timezone Inversion Hardening (LEAD-BE-03)
Three-Layer Logic Architecture (Paranoia Framework)

Covers:
- Layer 0: Foundational Layer (NANP area codes map to specific regional timezones, international prefixes)
- Layer 1: Environmental Failure Analysis (Blind '+' prepending on 10-digit US area codes does not invert,
          country/location hints anchor national numbers, domestic trunk prefixes stripped)
- Layer 2: Human Paranoia (Dirty formatting, extensions, poison location strings with phone fallback,
          graceful degradation when phonenumbers library is unavailable)
"""

import pytest
from unittest.mock import patch, MagicMock

from leads.backend.services.location_timezone_service import (
    LocationTimezoneService,
    POISON_LOCATIONS,
)


# ==============================================================================
# LAYER 0: FOUNDATIONAL LAYER
# ==============================================================================

class TestStage21Layer0FoundationalResolution:
    """Foundational tests for granular phone-to-timezone resolution."""

    @pytest.mark.parametrize(
        "phone_str, expected_iana",
        [
            ("(415) 555-0199", "America/Los_Angeles"),
            ("415-555-0199", "America/Los_Angeles"),
            ("+1 (415) 555-0199", "America/Los_Angeles"),
            ("(312) 555-0199", "America/Chicago"),
            ("(303) 555-0199", "America/Denver"),
            ("(212) 555-0199", "America/New_York"),
            ("(602) 555-0199", "America/Phoenix"),
            ("(206) 555-0199", "America/Los_Angeles"),
            ("(808) 555-0199", "Pacific/Honolulu"),
            ("(907) 555-0199", "America/Anchorage"),
        ],
    )
    def test_us_nanp_area_codes_resolve_to_specific_regional_timezones(self, phone_str, expected_iana):
        """10-digit North American area codes resolve to their exact regional timezones, not generic Eastern."""
        resolved = LocationTimezoneService.infer_timezone(location=None, phone=phone_str)
        assert resolved == expected_iana

    @pytest.mark.parametrize(
        "phone_str, expected_iana",
        [
            ("+44 20 7946 0958", "Europe/London"),
            ("+91 98765 43210", "Asia/Kolkata"),
            ("+33 1 42 68 55 55", "Europe/Paris"),
            ("+49 30 1234567", "Europe/Berlin"),
            ("+41 79 123 4567", "Europe/Zurich"),
            ("+61 2 9876 5432", "Australia/Sydney"),
            ("+81 3 1234 5678", "Asia/Tokyo"),
            ("+65 6123 4567", "Asia/Singapore"),
        ],
    )
    def test_international_phone_dial_codes(self, phone_str, expected_iana):
        """Standard E.164 international numbers with leading + resolve to target national timezones."""
        resolved = LocationTimezoneService.infer_timezone(location=None, phone=phone_str)
        assert resolved == expected_iana


# ==============================================================================
# LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
# ==============================================================================

class TestStage21Layer1EnvironmentalFailureAnalysis:
    """
    Environmental failure tests:
    - Blind '+' prepended to 10-digit US area codes (LEAD-BE-03)
    - Country hint anchoring for un-prefixed numbers
    - Location token anchoring
    """

    @pytest.mark.parametrize(
        "blind_plus_phone, expected_iana, inverted_trap",
        [
            ("+4155550199", "America/Los_Angeles", "Europe/Zurich"),  # 415 SF vs +41 Switzerland
            ("+9175550199", "America/New_York", "Asia/Kolkata"),       # 917 NYC vs +91 India
            ("+3305550199", "America/New_York", "Europe/Paris"),       # 330 Ohio vs +33 France
            ("+3125550199", "America/Chicago", "Europe/Amsterdam"),   # 312 Chicago vs +31 Netherlands
            ("+3475550199", "America/New_York", "Europe/Madrid"),      # 347 NYC vs +34 Spain
            ("+4705550199", "America/New_York", "Europe/Oslo"),        # 470 Atlanta vs +47 Norway
            ("+4805550199", "America/Phoenix", "Europe/Warsaw"),       # 480 Phoenix vs +48 Poland
        ],
    )
    def test_blind_plus_prepended_to_nanp_area_codes_does_not_invert(
        self, blind_plus_phone, expected_iana, inverted_trap
    ):
        """
        LEAD-BE-03 Verification:
        When a form or CRM prepends '+' to a 10-digit US number without the country code 1,
        the service must NOT invert it into Switzerland (+41), India (+91), France (+33), etc.
        """
        resolved = LocationTimezoneService.infer_timezone(location=None, phone=blind_plus_phone)
        assert resolved != inverted_trap, f"Inverted into {inverted_trap}!"
        assert resolved == expected_iana

    def test_country_hint_anchors_national_phone_numbers(self):
        """Country hint prevents national numbers from misinterpreting as US +1."""
        # 10-digit Indian number starting with 9 - must not turn into +1
        in_res = LocationTimezoneService.infer_timezone(
            location=None, country="India", phone="9876543210"
        )
        assert in_res == "Asia/Kolkata"

        # UK phone with domestic trunk 0
        uk_res = LocationTimezoneService.infer_timezone(
            location=None, country="United Kingdom", phone="07911 123456"
        )
        assert uk_res == "Europe/London"

        # France phone with domestic trunk 0
        fr_res = LocationTimezoneService.infer_timezone(
            location=None, country="France", phone="06 12 34 56 78"
        )
        assert fr_res == "Europe/Paris"

        # Germany phone with domestic trunk 0
        de_res = LocationTimezoneService.infer_timezone(
            location=None, country="Germany", phone="030 1234567"
        )
        assert de_res == "Europe/Berlin"

    def test_location_token_anchors_phone_when_country_omitted(self):
        """Location city/state tokens anchor phone parsing when country argument is omitted."""
        # Location in SF anchors +415... as US
        res_sf = LocationTimezoneService.infer_timezone(
            location="San Francisco, CA", phone="+4155550199"
        )
        assert res_sf == "America/Los_Angeles"

        # Location in Mumbai anchors 10-digit Indian number
        res_in = LocationTimezoneService.infer_timezone(
            location="Mumbai, Maharashtra", phone="9876543210"
        )
        assert res_in == "Asia/Kolkata"


# ==============================================================================
# LAYER 2: HUMAN PARANOIA & EDGE CASES
# ==============================================================================

class TestStage21Layer2HumanParanoiaAndResilience:
    """Human paranoia edge cases: extensions, poison locations, graceful fallback."""

    def test_dirty_phone_formatting_and_extensions(self):
        """Strips phone extensions, dots, spaces, and international 00 prefixes."""
        assert LocationTimezoneService.infer_timezone(
            location=None, phone="(415) 555-0199 ext 42"
        ) == "America/Los_Angeles"

        assert LocationTimezoneService.infer_timezone(
            location=None, phone="+1-312-555-0199 x101"
        ) == "America/Chicago"

        assert LocationTimezoneService.infer_timezone(
            location=None, phone="303.555.0199"
        ) == "America/Denver"

        assert LocationTimezoneService.infer_timezone(
            location=None, phone="0044 20 7946 0958"
        ) == "Europe/London"

    def test_poison_location_with_phone_resolution(self):
        """Poison locations (Remote, WFH) are ignored and phone resolves accurately."""
        assert LocationTimezoneService.infer_timezone(
            location="Remote", phone="(415) 555-0199"
        ) == "America/Los_Angeles"

        assert LocationTimezoneService.infer_timezone(
            location="WFH - Worldwide", phone="+91 98765 43210"
        ) == "Asia/Kolkata"

        assert LocationTimezoneService.infer_timezone(
            location="Global / Anywhere", phone="+44 20 7946 0958"
        ) == "Europe/London"

    def test_fallback_resilience_when_phonenumbers_is_mocked_unavailable(self):
        """
        When Google's phonenumbers library is missing or throws exceptions,
        the service falls back safely to built-in NANP & international dial tables.
        """
        with patch("leads.backend.services.location_timezone_service.phonenumbers", None):
            with patch("leads.backend.services.location_timezone_service.phone_timezone", None):
                # NANP Area code fallback
                assert LocationTimezoneService.resolve_phone_timezone(
                    phone="(415) 555-0199"
                ) == "America/Los_Angeles"

                assert LocationTimezoneService.resolve_phone_timezone(
                    phone="(312) 555-0199"
                ) == "America/Chicago"

                # International dial code fallback
                assert LocationTimezoneService.resolve_phone_timezone(
                    phone="+44 20 7946 0958"
                ) == "Europe/London"

                assert LocationTimezoneService.resolve_phone_timezone(
                    phone="+91 98765 43210"
                ) == "Asia/Kolkata"
