import pytest
from leads.backend.services.data_hygiene import DataHygieneService
from leads.backend.services.lead_segmentation_service import sanitize_text as seg_sanitize_text


class TestCsvFormulaInjectionDefense:
    """
    Paranoia Layer 0 & 2: Rigorously verifies that all formula injection vectors
    (=, +, -, @, \\t, \\r) are safely escaped with a single quote prefix across
    the DataHygieneService and Lead Segmentation export engines.
    """

    @pytest.mark.parametrize("payload,expected_prefix", [
        ("=cmd|' /C calc'!A0", "'="),
        ("+1234567890", "+"),  # Legitimate signed number should be preserved
        ("+SUM(A1:A10)", "'+"),  # Formula with + should be escaped
        ("-50.25", "-"),  # Legitimate negative float preserved
        ("-cmd|'/c calc'!A1", "'-"),
        ("@SUM(1,2)", "'@"),
        ("\tDDE('cmd')", "'"),
        ("=HYPERLINK(\"http://malicious.site\",\"Click Me\")", "'="),
    ])
    def test_data_hygiene_formula_neutralization(self, payload, expected_prefix):
        cleaned = DataHygieneService.sanitize_csv_cell(payload)
        assert cleaned.startswith(expected_prefix), f"Payload {payload} was not escaped with {expected_prefix}"

    def test_lead_segmentation_formula_neutralization(self):
        malicious_input = "=2+5*cmd|' /C calc'!A0"
        sanitized = seg_sanitize_text(malicious_input)
        assert sanitized.startswith("'="), "Formula was not safely prefixed with single quote in segmentation export"

    def test_null_and_empty_handling(self):
        assert DataHygieneService.sanitize_csv_cell(None) == ""
        assert DataHygieneService.sanitize_csv_cell("") == ""
        assert seg_sanitize_text(None) == ""
        assert seg_sanitize_text("") == ""
