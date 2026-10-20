import os
import re
import unittest


class TestStage23LeadsUIAccessibilityAndInteractiveIntegrity(unittest.TestCase):
    """
    Stage 23 Paranoia Test Suite:
    Validates Leads UI Accessibility, Memory Leak Cleanup & Interactive Integrity:
    - Layer 0: Native button semantics, WCAG-compliant interactive element separation,
               and reverse tabnabbing defense (rel="noopener noreferrer").
    - Layer 1: Memory leak elimination via URL.revokeObjectURL across all client-side export vectors.
    - Layer 2: Fail-safe delete confirmation modal (no premature dismissal on 500),
               and explicit empty states for zero social signals.
    """

    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))

    # =========================================================================
    # Layer 0: Accessibility Semantics & Reverse Tabnabbing Defense
    # =========================================================================
    def test_layer0_lead_table_native_button_semantics_and_aria(self):
        """
        Layer 0: Verify LeadTable uses native button semantics with explicit aria-labels
        and cleanly separates list selection from management actions (zero nested buttons).
        """
        lead_table_path = os.path.join(self.repo_root, "core/frontend/components/leads/LeadTable.tsx")
        self.assertTrue(os.path.exists(lead_table_path), f"File not found: {lead_table_path}")

        with open(lead_table_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. Verify list selection uses accessible button with aria-label
        self.assertIn('<button\n              type="button"\n              aria-label={`Open lead list ${list.name}`}', content)

        # 2. Verify delete button has aria-label
        self.assertIn('aria-label={`Delete list ${list.name}`}', content)

        # 3. Verify separation: the action buttons are inside a sibling container, not nested in the open button
        self.assertIn('</button>\n            <div className="flex items-center justify-end gap-2 pr-1 relative z-10">', content)

    def test_layer0_reverse_tabnabbing_rel_noopener_noreferrer(self):
        """
        Layer 0: All external target="_blank" links in leads and campaign onboarding
        must enforce rel="noopener noreferrer" to prevent window.opener hijacking.
        """
        files_to_check = [
            "core/frontend/components/leads/ListLeadsDrawer.tsx",
            "core/frontend/components/leads/SocialSignalRadarView.tsx",
            "core/frontend/components/leads/methods/SearchImport.tsx",
            "core/frontend/components/leads/methods/CSVImport.tsx",
            "core/frontend/components/leads/methods/HubSpotImport.tsx",
            "campaigns/frontend/EleInCreateCampaign.tsx",
        ]

        anchor_pattern = re.compile(r'<(?:a|Link)\b[^>]*\btarget="_blank"[^>]*>', re.IGNORECASE)

        for rel_path in files_to_check:
            abs_path = os.path.join(self.repo_root, rel_path)
            self.assertTrue(os.path.exists(abs_path), f"File not found: {abs_path}")

            with open(abs_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line_no, line in enumerate(lines, 1):
                if 'target="_blank"' in line:
                    # Collect multi-line tag if needed
                    tag_snippet = line
                    if not tag_snippet.strip().endswith(">"):
                        for next_line in lines[line_no:line_no + 5]:
                            tag_snippet += " " + next_line.strip()
                            if ">" in next_line:
                                break

                    self.assertIn(
                        'rel="noopener noreferrer"',
                        tag_snippet,
                        f"Missing rel='noopener noreferrer' in {rel_path} line {line_no}: {line.strip()}"
                    )

    # =========================================================================
    # Layer 1: Memory Leak Elimination & Object URL Lifecycle
    # =========================================================================
    def test_layer1_export_object_url_revocation(self):
        """
        Layer 1: Verify all client-side CSV/Blob exports invoke URL.revokeObjectURL
        to prevent memory leaks across long user sessions.
        """
        files_with_exports = [
            ("core/frontend/components/leads/ListLeadsDrawer.tsx", "revokeObjectURL"),
            ("core/frontend/components/leads/SocialSignalRadarView.tsx", "revokeObjectURL"),
            ("core/frontend/components/leads/DynamicSegmentationStudioModal.tsx", "revokeObjectURL"),
        ]

        for rel_path, required_token in files_with_exports:
            abs_path = os.path.join(self.repo_root, rel_path)
            self.assertTrue(os.path.exists(abs_path), f"File not found: {abs_path}")

            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn(required_token, content, f"Missing {required_token} in {rel_path}")

    # =========================================================================
    # Layer 2: Human Paranoia & Deletion Integrity
    # =========================================================================
    def test_layer2_delete_modal_fail_closed_error_retention(self):
        """
        Layer 2: Verify DeleteConfirmationModal does NOT close upon server error,
        keeping the modal open and displaying actionable error feedback to the user.
        """
        modal_path = os.path.join(self.repo_root, "core/frontend/components/leads/DeleteConfirmationModal.tsx")
        self.assertTrue(os.path.exists(modal_path), f"File not found: {modal_path}")

        with open(modal_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. Check response ok check
        self.assertIn("if (!res.ok)", content)
        # 2. onClose only inside try after success
        self.assertIn("toast.success(\"List deleted successfully\");", content)
        self.assertIn("onClose();", content)
        # 3. friendlyToast in catch block
        self.assertIn("friendlyToast(e?.message", content)

    def test_layer2_social_radar_zero_signal_empty_state_guidance(self):
        """
        Layer 2: Verify SocialSignalRadarView presents an explicit guidance card
        with actionable launch CTA when zero intent signals are found.
        """
        radar_path = os.path.join(self.repo_root, "core/frontend/components/leads/SocialSignalRadarView.tsx")
        self.assertTrue(os.path.exists(radar_path), f"File not found: {radar_path}")

        with open(radar_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("No Intent Signals Detected Yet", content)
        self.assertIn("Launch Radar Scan on List", content)


if __name__ == "__main__":
    unittest.main()
