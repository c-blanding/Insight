import unittest
from pathlib import Path

from insightai.evaluation.runner import (
    _validate_cases,
    _origin,
    load_cases,
    score_record,
    summarize,
)


class BenchmarkDefinitionTests(unittest.TestCase):
    def test_cases_have_unique_ids_and_expected_labels(self):
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 5)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertTrue({"bug", "no_bug", "inconclusive"}.issubset(
            {case["category"] for case in cases}
        ))

    def test_rejects_duplicate_case_ids(self):
        payload = {
            "schema_version": 1,
            "cases": [
                {"id": "same", "category": "bug", "path": "/", "bug_description": "x", "expected_verdict": "bug_confirmed"},
                {"id": "same", "category": "bug", "path": "/", "bug_description": "x", "expected_verdict": "bug_confirmed"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            _validate_cases(payload, source=Path("cases.json"))


class BenchmarkScoringTests(unittest.TestCase):
    def test_origin_omits_credentials_and_paths(self):
        self.assertEqual(
            _origin("https://user:secret@example.test:8443/path?token=hidden"),
            "https://example.test:8443",
        )

    def test_bug_requires_correct_verdict_path_and_observation(self):
        base = {
            "category": "bug",
            "expected_verdict": "bug_confirmed",
            "actual_verdict": "bug_confirmed",
            "key_path_reached": True,
            "evidence": {"observable_evidence": True},
        }
        self.assertTrue(score_record(base.copy())["bug_reproduced"])
        base["key_path_reached"] = False
        self.assertFalse(score_record(base)["bug_reproduced"])

    def test_summary_handles_all_denominators_and_records_false_positive(self):
        summary = summarize([
            {
                "category": "bug",
                "expected_verdict": "bug_confirmed",
                "actual_verdict": "bug_confirmed",
                "key_path_reached": True,
                "evidence": {"observable_evidence": True},
                "report_cites_evidence": True,
                "tool_call_count": 4,
                "duration_seconds": 10,
                "status": "completed",
            },
            {
                "category": "no_bug",
                "expected_verdict": "not_reproduced",
                "actual_verdict": "bug_confirmed",
                "key_path_reached": True,
                "evidence": {"observable_evidence": True},
                "report_cites_evidence": False,
                "tool_call_count": 2,
                "duration_seconds": 6,
                "status": "completed",
            },
            {
                "category": "auth_recovery",
                "expected_verdict": "bug_confirmed",
                "actual_verdict": "inconclusive",
                "key_path_reached": False,
                "evidence": {"observable_evidence": False},
                "report_cites_evidence": False,
                "tool_call_count": 1,
                "duration_seconds": 3,
                "login_recovery": "paused",
                "status": "needs_login",
            },
        ])
        self.assertEqual(summary["bug_reproduction_rate"], 1.0)
        self.assertEqual(summary["false_positive_rate"], 1.0)
        self.assertIsNone(summary["correct_inconclusive_rate"])
        self.assertIsNone(summary["login_recovery_rate"])


if __name__ == "__main__":
    unittest.main()
