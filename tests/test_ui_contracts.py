"""Headless unit tests for the redesigned UI design tokens, i18n strings, and approval presentation contracts."""
from __future__ import annotations

import unittest

from orchestra.desktop import STATES
from orchestra.execution_state import INCOMPLETE, LIVE, TERMINAL
from orchestra.ui.strings import LOCALES, NAV_GROUPS, STATES_I18N, STRINGS, state_label, t
from orchestra.ui.theme import THEMES, approval_state_info, status_tone


class UIContractsTest(unittest.TestCase):
    def test_dark_and_light_themes_share_all_required_tokens(self):
        required_keys = {
            "name", "canvas", "sidebar", "sidebar_border", "header", "panel", "elevated",
            "hover", "active", "border", "border_strong", "text", "text_secondary", "muted",
            "accent", "accent_hover", "accent_text", "danger", "danger_hover",
            "nav_fg", "nav_muted", "nav_active_fg", "terminal_bg", "terminal_fg",
            "tree_selected", "graph_bg", "graph_edge", "badges", "graph_nodes",
        }
        dark_keys = set(THEMES["dark"])
        light_keys = set(THEMES["light"])
        self.assertTrue(required_keys.issubset(dark_keys))
        self.assertEqual(dark_keys, light_keys)
        for theme_name in ("dark", "light"):
            palette = THEMES[theme_name]
            self.assertEqual(set(palette["badges"]), {"success", "running", "warning", "danger", "neutral"})
            self.assertEqual(
                set(palette["graph_nodes"]),
                {"SUCCEEDED", "RUNNING", "VERIFYING", "PREPARING", "FAILED", "AWAITING_TOOL",
                 "AWAITING_APPROVAL", "CANCELLED", "NOT_EXECUTED", "QUEUED"},
            )

    def test_strings_locales_and_navigation_groups_are_complete(self):
        self.assertEqual(LOCALES, ("ko", "en"))
        self.assertEqual(set(STRINGS["ko"]), set(STRINGS["en"]))
        for locale in LOCALES:
            for key, value in STRINGS[locale].items():
                self.assertTrue(isinstance(value, str) and value.strip(), f"empty string for {locale}:{key}")

        nav_keys = [item_key for _, items in NAV_GROUPS for item_key, _ in items]
        self.assertIn("workspace", nav_keys)
        self.assertEqual(len(nav_keys), len(set(nav_keys)))
        for _, items in NAV_GROUPS:
            for item_key, str_key in items:
                for locale in LOCALES:
                    resolved = t(str_key, locale)
                    self.assertNotEqual(resolved, str_key, f"missing translation for {item_key} -> {str_key}")
        self.assertEqual(t("nonexistent.key", "en"), "nonexistent.key")

    def test_state_labels_and_tones_cover_all_execution_states(self):
        all_states = set(STATES) | set(LIVE) | set(INCOMPLETE) | set(TERMINAL)
        self.assertEqual(set(STATES_I18N["ko"]), set(STATES_I18N["en"]))
        for locale in LOCALES:
            self.assertTrue(all_states.issubset(set(STATES_I18N[locale])), f"missing state translations in {locale}")
        for state in all_states:
            self.assertIn(status_tone(state), {"success", "running", "warning", "danger", "neutral"})
            self.assertTrue(state_label(state, "ko"))
            self.assertTrue(state_label(state, "en"))
        self.assertEqual(status_tone(None), "neutral")

    def test_approval_state_info_covers_all_authoritative_states(self):
        code, _, tone, eligible, blockers = approval_state_info(None)
        self.assertEqual((code, tone, eligible), ("WAITING_QA", "neutral", False))
        self.assertTrue(blockers)

        for state, expected_code, expected_tone in (
            ("MERGED", "MERGED", "success"),
            ("MERGE_QUEUED", "MERGING", "running"),
            ("MERGING", "MERGING", "running"),
            ("CANCELLED", "REJECTED", "danger"),
            ("FAILED", "QA_FAILED", "danger"),
            ("SUCCEEDED", "COMPLETED", "neutral"),
            ("VERIFYING", "WAITING_QA", "running"),
        ):
            code, _, tone, eligible, _ = approval_state_info({"state": state, "result": {}, "plan": {"tasks": []}})
            self.assertEqual((code, tone, eligible), (expected_code, expected_tone, False))

        # Reviewer still active while job is running -> WAITING_REVIEW
        running_job = {"state": "RUNNING", "plan": {"tasks": [{"id": "rev", "role": "reviewer"}]}}
        code, _, tone, eligible, _ = approval_state_info(running_job, tasks={"rev": {"state": "RUNNING"}})
        self.assertEqual((code, tone, eligible), ("WAITING_REVIEW", "warning", False))

        # AWAITING_APPROVAL without valid QA / candidate -> blocked
        blocked_job = {"state": "AWAITING_APPROVAL", "result": {"candidate": ""}, "plan": {"tasks": []}}
        code, _, tone, eligible, blockers = approval_state_info(blocked_job)
        self.assertEqual((code, tone, eligible), ("QA_FAILED", "danger", False))
        self.assertTrue(blockers)

        # AWAITING_APPROVAL with valid candidate & passing QA -> READY
        ready_job = {
            "state": "AWAITING_APPROVAL",
            "result": {
                "candidate": "a" * 40,
                "approval_revision": "rev-1",
                "qa": [{"index": 1, "exit_code": 0}],
            },
            "plan": {"tasks": []},
        }
        code, _, tone, eligible, blockers = approval_state_info(ready_job)
        self.assertEqual((code, tone, eligible), ("READY", "success", True))
        self.assertEqual(blockers, [])


if __name__ == "__main__":
    unittest.main()
