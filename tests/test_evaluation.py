"""Editorial labels must support every reported quality metric."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from promo_finder.evaluation import compare_runs, review_metrics


class ReviewMetricTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def sheet(self, labels, *, ranks=None, reasons=None):
        path = self.root / "review.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["id", "rank", "label", "reason"])
            writer.writeheader()
            for index, label in enumerate(labels):
                writer.writerow({"id": f"fixture-{index}", "rank": ranks[index] if ranks else index + 1, "label": label, "reason": reasons[index] if reasons else "A review reason."})
        return path

    def test_unlabelled_sheet_reports_no_accuracy_number(self):
        result = review_metrics(self.sheet([""] * 24))
        self.assertEqual(result["labelled"], 0)
        self.assertEqual(result["unlabelled"], 24)
        for field in ("strict_good_fraction", "usable_good_or_okay_fraction", "precision_at_10_strict", "strict_good_wilson_95_interval_descriptive_only"):
            self.assertIsNone(result[field], field)

    def test_case_and_spaces_normalize_without_counting_blank_as_bad(self):
        result = review_metrics(self.sheet([" GOOD ", "Okay", "BAD", " ", "good"], reasons=["a", "", "c", "", "d"]))
        self.assertEqual(result["counts"], {"good": 2, "okay": 1, "bad": 1})
        self.assertEqual(result["labelled"], 4)
        self.assertEqual(result["unlabelled"], 1)
        self.assertEqual(result["strict_good_fraction"], .5)
        self.assertEqual(result["usable_good_or_okay_fraction"], .75)
        self.assertEqual(result["missing_reason_count"], 1)
        self.assertIsNone(result["precision_at_10_strict"])

    def test_invalid_labels_fail_rather_than_disappear(self):
        for label in ("great", "1", "yes", "not bad"):
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, "Invalid label"):
                review_metrics(self.sheet([label]))

    def test_precision_at_ten_requires_all_ten_actual_ranks_labelled(self):
        complete = review_metrics(self.sheet(["good"] * 7 + ["okay", "bad", "bad"] + [""] * 2))
        self.assertEqual(complete["precision_at_10_strict"], .7)
        incomplete = review_metrics(self.sheet(["good"] * 9 + [""] + ["good"] * 2))
        self.assertIsNone(incomplete["precision_at_10_strict"])
        nine_only = review_metrics(self.sheet(["good"] * 9))
        self.assertIsNone(nine_only["precision_at_10_strict"])
        missing_middle_rank = review_metrics(self.sheet(["good"] * 10, ranks=[1, 2, 3, 4, 5, 7, 8, 9, 10, 11]))
        self.assertIsNone(missing_middle_rank["precision_at_10_strict"])

    def test_duplicate_or_nonpositive_ranks_cannot_fake_complete_top_ten(self):
        with self.assertRaises(ValueError):
            review_metrics(self.sheet(["good"] * 10, ranks=[1] * 10))
        for rank in (0, -1):
            with self.subTest(rank=rank), self.assertRaises(ValueError):
                review_metrics(self.sheet(["good"], ranks=[rank]))

    def test_duplicate_ids_rejected(self):
        path = self.sheet(["good", "bad"])
        text = path.read_text(encoding="utf-8-sig").replace("fixture-1", "fixture-0")
        path.write_text(text, encoding="utf-8-sig")
        with self.assertRaisesRegex(ValueError, "Duplicate review IDs"):
            review_metrics(path)


class StabilityMetricTests(unittest.TestCase):
    def record(self, identifier, start=0):
        return {"id": identifier, "segments": [{"episode": 1, "start_ms": start, "end_ms": start + 20000}], "duration_ms": 20000, "judgment": {"resolved": False}}

    def write_run(self, root, name, promos):
        path = root / name
        path.mkdir()
        value = {"run": {"judgment_mode": "test_fixture_NOT_LLM", "config": {"provider": "mock"}, "variant": "refined"}, "retrieval": {}, "usage": {}, "validation": {"ranked": {"episodes_represented": [1], "types": {"other": len(promos)}}}, "promos": promos}
        (path / "promos.json").write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_identical_runs_have_exact_stability(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [self.write_run(root, name, [self.record("same")]) for name in ("a", "b")]
            result = compare_runs(paths)
        row = result["comparisons"][0]
        self.assertEqual(row["exact_jaccard"], 1)
        self.assertEqual(row["overlap_of_smaller_top_k"], 1)
        self.assertTrue(row["same_first_pick"])

    def test_relaxed_overlap_is_one_to_one_and_separate_from_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a = self.write_run(root, "a", [self.record("a")])
            b = self.write_run(root, "b", [self.record("b", 1000), self.record("c", 2000)])
            result = compare_runs([a, b])
        row = result["comparisons"][0]
        self.assertEqual(row["exact_common"], 0)
        self.assertEqual(row["exact_jaccard"], 0)
        self.assertEqual(row["relaxed_one_to_one_matches_80_percent"], 1)
        self.assertFalse(row["same_first_pick"])

    def test_comparison_requires_two_runs(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            compare_runs([])


if __name__ == "__main__":
    unittest.main()
