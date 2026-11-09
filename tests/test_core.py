"""Behavioral checks for timing, evidence, model failures and offline runs."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from promo_finder.candidates import generate, make_candidate, temporal_overlap
from promo_finder.judging import judged, mock_judgment, parse_judgment, rank, score
from promo_finder.pipeline import run
from promo_finder.source import parse_text
from promo_finder.validation import audit, validate


SCRIPT = '''EPISODE NUMBER: Episode 1
EPISODE LOGLINE: A synthetic dispute over a missing crown.
--- SCRIPT START ---
SCENE 01
Scene start: 00:00.00
Scene end: 01:20.00
Actions and dialogue:
**CAMERA:**
Start: (00:00.00) | End: (01:20.00)
Two people stand by a door.
**ALICE (Angry):**
Start: (00:00.00) | End: (00:02.00)
"You stole my crown!"
**ACTION:**
Start: (00:02.00) | End: (00:04.00)
Alice raises a key.
**BOB (Alarmed):**
Start: (00:18.00) | End: (00:20.00)
"Who opened that door?"
**ALICE (Urgent):**
Start: (00:20.00) | End: (00:23.00)
"The guard is here!"
**ACTION:**
Start: (00:23.00) | End: (00:25.00)
Bob reaches for the key.
**BOB (Afraid):**
Start: (00:38.00) | End: (00:40.00)
"Will you have me arrested?"
**ACTION:**
Start: (00:58.00) | End: (01:00.00)
Alice opens the locked door.
--- SCRIPT END ---
'''

GOOD_JUDGMENT = {"hook": 4, "cliffhanger": 4, "clarity": 3, "emotion": 3, "premise": 4, "spoiler": 1, "resolved": False, "type": "danger", "why": "An accusation creates an immediate dispute before an unanswered threat.", "risk": "The key may need a clearer visual introduction."}


def fixture(number=1):
    return parse_text(SCRIPT.replace("Episode 1", f"Episode {number}"), f"episode-{number:03d}.txt")


def candidate(ep, start=0, end=20000):
    return make_candidate({ep.number: ep}, [{"episode": ep.number, "start_ms": start, "end_ms": end}], "refined")


def scored(c, judgment=None):
    c = deepcopy(c)
    c["judgment"] = deepcopy(judgment or GOOD_JUDGMENT)
    c["score"] = score(c, c["judgment"])
    return c


class BoundariesTests(unittest.TestCase):
    def test_inclusive_duration_limits_and_real_cut_points(self):
        ep = fixture()
        for end in (20000, 60000):
            with self.subTest(end=end):
                c = candidate(ep, end=end)
                self.assertIsNotNone(c)
                self.assertTrue(validate(c, {1: ep})["passed"])
        self.assertIsNone(candidate(ep, end=19999))
        self.assertIsNone(candidate(ep, end=60001))
        self.assertIsNone(candidate(ep, end=20001))

    def test_end_is_exclusive_and_does_not_include_next_answer(self):
        ep = fixture()
        c = candidate(ep)
        self.assertEqual(c["cliffhanger"]["quote"], '"Who opened that door?"')
        ids_in_clip = {e["id"] for e in c["transcript"][0]["events"]}
        answer = next(e for e in ep.events if e.start == 20000)
        self.assertNotIn(answer.id, ids_in_clip)
        self.assertIn(answer.id, {e["id"] for e in c["after"]})

    def test_fabricated_boundary_and_quote_are_rejected(self):
        ep = fixture()
        c = candidate(ep)
        forged = deepcopy(c)
        forged["segments"][0]["end_ms"] = 20001
        forged["duration_ms"] = 20001
        self.assertFalse(validate(forged, {1: ep})["checks"]["timestamp_validity"])
        forged = deepcopy(c)
        forged["hook"]["quote"] = "A line that never occurred."
        self.assertFalse(validate(forged, {1: ep})["checks"]["quote_verification"])

    def test_hook_and_cliffhanger_metadata_cannot_invent_timestamps(self):
        ep = fixture()
        original = candidate(ep)
        for field in ("hook", "cliffhanger"):
            for timestamp in ("start_ms", "end_ms"):
                forged = deepcopy(original)
                forged[field][timestamp] += 1
                with self.subTest(field=field, timestamp=timestamp):
                    self.assertFalse(validate(forged, {1: ep})["checks"]["quote_verification"])

    def test_long_spoken_hook_cannot_claim_first_three_seconds(self):
        ep = parse_text(SCRIPT.replace("End: (00:02.00)", "End: (00:04.00)").replace("Start: (00:02.00)", "Start: (00:04.00)").replace("End: (00:04.00)\nAlice raises", "End: (00:05.00)\nAlice raises"), "episode-001.txt")
        self.assertIsNone(candidate(ep))

    def test_dialogue_cannot_be_cut_even_at_a_camera_boundary(self):
        script = SCRIPT.replace("Start: (00:02.00) | End: (00:04.00)", "Start: (00:01.00) | End: (00:04.00)")
        ep = parse_text(script, "episode-001.txt")
        self.assertIn(1000, ep.boundaries)
        self.assertIsNone(candidate(ep, start=1000, end=40000))
        forged = candidate(ep)
        forged["segments"][0]["start_ms"] = 1000
        forged["segments"][0]["end_ms"] = 40000
        forged["duration_ms"] = 39000
        self.assertFalse(validate(forged, {1: ep})["checks"]["no_speech_truncation"])

    def test_segment_order_and_self_overlap_are_rejected(self):
        ep = fixture()
        c = candidate(ep)
        c["segments"] = [{"episode": 1, "start_ms": 20000, "end_ms": 40000}, {"episode": 1, "start_ms": 0, "end_ms": 20000}]
        c["duration_ms"] = 40000
        self.assertFalse(validate(c, {1: ep})["checks"]["ordering"])
        c["segments"] = [{"episode": 1, "start_ms": 0, "end_ms": 20000}] * 2
        self.assertFalse(validate(c, {1: ep})["checks"]["ordering"])

    def test_cross_episode_reverse_order_rejected(self):
        ep1, ep2 = fixture(), fixture(2)
        c = candidate(ep1)
        c["segments"] = [{"episode": 2, "start_ms": 0, "end_ms": 20000}, {"episode": 1, "start_ms": 0, "end_ms": 20000}]
        c["duration_ms"] = 40000
        self.assertFalse(validate(c, {1: ep1, 2: ep2})["checks"]["ordering"])


class RankingTests(unittest.TestCase):
    def test_duplicate_and_near_overlap_suppression(self):
        ep = fixture()
        short, long = scored(candidate(ep)), scored(candidate(ep, end=60000))
        self.assertEqual(temporal_overlap(short, long), 1)
        self.assertEqual(len(rank([short, long], limit=10)), 1)
        report = audit([short, deepcopy(short)], {1: ep}, selected=True)
        self.assertEqual(report["exact_duplicates"], 1)
        self.assertFalse(report["all_invariants_pass"])

    def test_resolved_ending_lowers_score(self):
        c = candidate(fixture())
        open_score = score(c, GOOD_JUDGMENT)
        resolved = GOOD_JUDGMENT | {"resolved": True}
        self.assertEqual(open_score["base_score"] - score(c, resolved)["base_score"], 15)

    def test_generation_covers_each_episode_and_preserves_invariants(self):
        episodes = [fixture(), fixture(2)]
        candidates, info = generate(episodes, per_episode=2)
        self.assertEqual({s["episode"] for c in candidates for s in c["segments"]}, {1, 2})
        self.assertTrue(audit(candidates, {e.number: e for e in episodes})["all_invariants_pass"])
        self.assertTrue(all(info["per_episode"][str(e.number)]["generated"] > 0 for e in episodes))


class JudgmentTests(unittest.TestCase):
    def test_missing_out_of_range_and_boolean_scores_rejected(self):
        variants = [GOOD_JUDGMENT | {"hook": 6}, GOOD_JUDGMENT | {"hook": True}, GOOD_JUDGMENT | {"resolved": "false"}, GOOD_JUDGMENT | {"type": "explosion"}, {k: v for k, v in GOOD_JUDGMENT.items() if k != "why"}]
        for obj in variants:
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                parse_judgment(json.dumps(obj))
        with self.assertRaises(ValueError):
            parse_judgment(json.dumps(GOOD_JUDGMENT | {"why": 'Someone says "an invented line".'}))

    def test_schema_failure_never_falls_back_to_offline_scores(self):
        class InvalidProvider:
            calls = 0
            def complete(self, messages, purpose="judge"):
                self.calls += 1
                return {"content": '{"hook":999}', "input_tokens": 1, "output_tokens": 1, "token_count_method": "test_fixture"}
        provider, log = InvalidProvider(), []
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "failed twice"):
                judged(candidate(fixture()), provider, {"provider": "test_fixture"}, "Synthetic premise", Path(folder), log, fresh=True)
        self.assertEqual(provider.calls, 2)
        self.assertEqual(len(log), 2)
        self.assertTrue(all("validation_error" in record for record in log))

    def test_valid_model_schema_and_cache_preserve_raw_response(self):
        class FixedProvider:
            calls = 0
            def complete(self, messages, purpose="judge"):
                self.calls += 1
                return {"content": json.dumps(GOOD_JUDGMENT), "input_tokens": 12, "output_tokens": 34, "token_count_method": "test_fixture"}
        provider, log = FixedProvider(), []
        with tempfile.TemporaryDirectory() as folder:
            args = (candidate(fixture()), provider, {"provider": "test_fixture"}, "Synthetic premise", Path(folder), log)
            self.assertEqual(judged(*args), GOOD_JUDGMENT)
            self.assertEqual(judged(*args), GOOD_JUDGMENT)
        self.assertEqual(provider.calls, 1)
        self.assertFalse(log[0]["cache_hit"])
        self.assertTrue(log[1]["cache_hit"])
        self.assertEqual(json.loads(log[0]["response"]["content"]), GOOD_JUDGMENT)


class PipelineTests(unittest.TestCase):
    def test_offline_run_writes_unedited_outputs_and_blank_review_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "episode-001.txt"
            source.write_text(SCRIPT, encoding="utf-8")
            result = run(source, root / "out", {"provider": "mock"}, per_episode=2, limit=10, progress=None)
            self.assertEqual(result["run"]["judgment_mode"], "offline_retrieval_proxy_NOT_LLM")
            self.assertEqual(result["usage"]["model_requests"], 0)
            self.assertTrue(result["validation"]["ranked"]["all_invariants_pass"])
            saved = json.loads((root / "out" / "promos.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, result)
            exported_rows = list(csv.DictReader(io.StringIO((root / "out" / "promos.csv").read_text(encoding="utf-8-sig"))))
            by_id = {promo["id"]: promo for promo in saved["promos"]}
            self.assertTrue(exported_rows)
            for row in exported_rows:
                promo = by_id[row["id"]]
                # Quote fields used to be overwritten by equally named numeric
                # dimensions during dict expansion. Keep both representations.
                self.assertEqual(row["hook"], promo["hook"]["quote"])
                self.assertEqual(row["cliffhanger"], promo["cliffhanger"]["quote"])
                for dimension, value in promo["score"]["dimensions_0_to_5"].items():
                    self.assertEqual(int(row[f"{dimension}_score"]), value)
            for name in ("promos.csv", "report.md", "review_sheet.csv", "validation.json", "source_manifest.json", "usage.json", "model_calls.json"):
                self.assertTrue((root / "out" / name).is_file(), name)
            rows = list(csv.DictReader(io.StringIO((root / "out" / "review_sheet.csv").read_text(encoding="utf-8-sig"))))
            self.assertTrue(rows)
            for row in rows:
                for column in ("label", "reason", "hook_within_3s", "unresolved_end", "standalone", "video_checked"):
                    self.assertEqual(row[column], "")
            for promo in saved["promos"]:
                for segment in promo["segments"]:
                    self.assertEqual(segment["start"], fixture().boundaries[segment["start_ms"]])
                    self.assertEqual(segment["end"], fixture().boundaries[segment["end_ms"]])
            with self.assertRaisesRegex(ValueError, "not empty"):
                run(source, root / "out", {"provider": "mock"}, progress=None)

    def test_source_fingerprint_does_not_depend_on_shortlist_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "episode-001.txt"
            source.write_text(SCRIPT, encoding="utf-8")
            one = run(source, root / "one", {"provider": "mock"}, per_episode=1, progress=None)
            two = run(source, root / "two", {"provider": "mock"}, per_episode=2, progress=None)
            self.assertNotEqual(len(one["candidates"]), len(two["candidates"]))
            self.assertEqual(one["run"]["input_pack_fingerprint"], two["run"]["input_pack_fingerprint"])

    def test_episode_count_mismatch_creates_no_success_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "episode-001.txt"
            source.write_text(SCRIPT, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Expected 50"):
                run(source, root / "out", {"provider": "mock"}, expected_episodes=50, progress=None)
            self.assertFalse((root / "out" / "promos.json").exists())

    def test_upload_run_keeps_download_bytes_after_temp_files_removed(self):
        from app import execute_uploads, validate_uploads
        result, downloads = execute_uploads([("episode-001.txt", SCRIPT.encode())], {"provider": "mock", "allow_remote": False}, per_episode=1, limit=2, stitches=False, expected_episodes=1)
        self.assertTrue(result["promos"])
        self.assertEqual(json.loads(downloads["promos.json"]), result)
        for files in ([('../escape.txt', b'x')], [('a.txt', b'x'), ('A.txt', b'y')], [('a.txt', b'')]):
            with self.subTest(files=files), self.assertRaises(ValueError):
                validate_uploads(files)

    def test_app_forwards_local_critic_count_and_forces_offline_to_zero(self):
        from unittest.mock import patch
        from app import DOWNLOADS, execute_uploads
        calls = []

        def fake_run(input_path, output_path, config, **kwargs):
            calls.append(kwargs)
            output_path.mkdir()
            for name in DOWNLOADS:
                (output_path / name).write_bytes(b"synthetic fixture")
            return {"test_fixture": True}

        with patch("app.run", side_effect=fake_run):
            for provider in ("openai_compatible", "mock"):
                execute_uploads([("episode-001.txt", SCRIPT.encode())], {"provider": provider, "allow_remote": False}, per_episode=1, limit=40, stitches=False, expected_episodes=1, critic_top=30)
        self.assertEqual(calls[0]["critic_top"], 30)
        self.assertEqual(calls[1]["critic_top"], 0)


if __name__ == "__main__":
    unittest.main()
