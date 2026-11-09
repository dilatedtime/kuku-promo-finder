"""Real-provider paths with deterministic synthetic stubs, never real API calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from promo_finder.critic import apply, parse
from promo_finder.judging import check_role_support, judged, judge_premise
from promo_finder.pipeline import run
from test_core import candidate, fixture, scored, GOOD_JUDGMENT


VERDICT = {"clarity": 2, "cliffhanger": 1, "resolved": True, "summary": "Alice accuses Bob of taking her crown and hears a question about a door.", "risk": "The final question introduces a door without explaining its stakes."}


class StubProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages, purpose="judge"):
        self.calls.append({"messages": deepcopy(messages), "purpose": purpose})
        content = self.responses.pop(0)
        return {"content": content, "input_tokens": 10, "output_tokens": 20, "token_count_method": "synthetic_test_fixture"}


class IsolatedJudgeTests(unittest.TestCase):
    def test_primary_judge_sees_clip_without_premise_before_or_after(self):
        clip = candidate(fixture())
        clip["after"] = [{"text": "AFTER_SENTINEL_secret_answer"}]
        clip["before"] = [{"text": "BEFORE_SENTINEL_secret_setup"}]
        provider, logs = StubProvider([json.dumps(GOOD_JUDGMENT), '{"premise": 4}']), []
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            judged(clip, provider, {"provider": "test_fixture"}, "PREMISE_SENTINEL_later_identity", cache, logs, fresh=True)
            representation = judge_premise(clip, provider, {"provider": "test_fixture"}, "PREMISE_SENTINEL_later_identity", cache, logs, fresh=True)
        primary = json.dumps(provider.calls[0]["messages"])
        separate = json.dumps(provider.calls[1]["messages"])
        self.assertNotIn("PREMISE_SENTINEL", primary)
        self.assertNotIn("AFTER_SENTINEL", primary)
        self.assertNotIn("BEFORE_SENTINEL", primary)
        self.assertIn("You stole my crown", primary)
        self.assertIn("PREMISE_SENTINEL", separate)
        self.assertNotIn("AFTER_SENTINEL", separate)
        self.assertEqual([call["purpose"] for call in provider.calls], ["judge", "premise"])
        self.assertEqual(representation, 4)

    def test_premise_schema_repair_preserves_original_attempt_and_cache(self):
        provider, logs = StubProvider(['{"premise": 99}', '{"premise": 3}']), []
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "new-cache-directory"
            args = (candidate(fixture()), provider, {"provider": "test_fixture"}, "Synthetic premise", cache, logs)
            self.assertEqual(judge_premise(*args), 3)
            self.assertEqual(len(provider.calls), 2)
            self.assertEqual(logs[0]["messages"], provider.calls[0]["messages"])
            self.assertEqual(len(logs[0]["messages"]), 2)
            self.assertEqual(len(logs[1]["messages"]), 4)
            self.assertIn("validation_error", logs[0])
            self.assertEqual(judge_premise(*args), 3)
            self.assertEqual(len(provider.calls), 2)
            self.assertTrue(logs[-1]["cache_hit"])

    def test_invalid_premise_boolean_does_not_become_a_score(self):
        provider, logs = StubProvider(['{"premise": true}', '{"premise": true}']), []
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError, "schema failed"):
            judge_premise(candidate(fixture()), provider, {"provider": "test_fixture"}, "Synthetic premise", Path(folder), logs)
        self.assertEqual(len(provider.calls), 2)


class RoleSupportTests(unittest.TestCase):
    def relationship_clip(self):
        from test_core import SCRIPT
        from promo_finder.source import parse_text
        source = SCRIPT.replace('"You stole my crown!"', '"You betrayed your husband!"')
        return candidate(parse_text(source, "episode-001.txt"))

    def test_absent_brother_is_rejected_but_present_husband_is_allowed(self):
        clip = self.relationship_clip()
        with self.assertRaisesRegex(ValueError, "brother"):
            check_role_support(GOOD_JUDGMENT | {"why": "Her brother faces an accusation."}, clip)
        check_role_support(GOOD_JUDGMENT | {"why": "Her husband faces an accusation."}, clip)

    def test_literal_role_guard_does_not_validate_other_story_claims(self):
        # This deliberately unsupported synthetic claim passes the narrow guard:
        # the role word is present, while arbitrary facts need semantic review.
        check_role_support(GOOD_JUDGMENT | {"why": "Her husband flies to Mars."}, self.relationship_clip())

    def test_fresh_unsupported_role_gets_a_real_repair_attempt(self):
        bad = GOOD_JUDGMENT | {"why": "Her brother faces an accusation."}
        good = GOOD_JUDGMENT | {"why": "Her husband faces an accusation."}
        provider, logs = StubProvider([json.dumps(bad), json.dumps(good)]), []
        with tempfile.TemporaryDirectory() as folder:
            result = judged(self.relationship_clip(), provider, {"provider": "test_fixture"}, "Synthetic premise", Path(folder), logs, fresh=True)
        self.assertEqual(result, good)
        self.assertEqual(len(provider.calls), 2)
        self.assertIn("brother", logs[0]["validation_error"])
        self.assertEqual(json.loads(logs[0]["response"]["content"]), bad)
        self.assertEqual(logs[0]["messages"], provider.calls[0]["messages"])
        self.assertEqual(len(logs[0]["messages"]), 2)

    def test_bad_cached_role_is_repaired_and_raw_bad_attempt_is_retained(self):
        bad = GOOD_JUDGMENT | {"why": "Her brother faces an accusation."}
        good = GOOD_JUDGMENT | {"why": "Her husband faces an accusation."}
        config, clip = {"provider": "test_fixture"}, self.relationship_clip()
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            judged(clip, StubProvider([json.dumps(good)]), config, "Synthetic premise", cache, [], fresh=True)
            path = next(cache.glob("*.json"))
            # Simulate a cache record accepted before the literal guard existed.
            old_record = json.loads(path.read_text(encoding="utf-8"))
            old_record["response"]["content"] = json.dumps(bad)
            path.write_text(json.dumps(old_record), encoding="utf-8")
            provider, logs = StubProvider([json.dumps(good)]), []
            result = judged(clip, provider, config, "Synthetic premise", cache, logs)
            repaired_cache = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(result, good)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(len(logs), 2)
        self.assertTrue(logs[0]["cache_hit"])
        self.assertFalse(logs[1]["cache_hit"])
        self.assertIn("brother", logs[0]["validation_error"])
        self.assertEqual(json.loads(logs[0]["response"]["content"]), bad)
        self.assertEqual(logs[0]["messages"], old_record["messages"])
        self.assertEqual(len(logs[0]["messages"]), 2)
        self.assertEqual(len(provider.calls[0]["messages"]), 4)
        self.assertEqual(json.loads(repaired_cache["response"]["content"]), good)


class CriticSchemaTests(unittest.TestCase):
    def test_valid_schema_has_no_quoted_story_lines(self):
        self.assertEqual(parse(json.dumps(VERDICT)), VERDICT)
        for bad in (VERDICT | {"clarity": True}, VERDICT | {"cliffhanger": 6}, VERDICT | {"resolved": "true"}, VERDICT | {"summary": 'Alice says "an invented quote".'}, VERDICT | {"risk": ""}, [], None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse(json.dumps(bad))

    def test_critic_uses_only_clip_and_can_lower_scores(self):
        c = scored(candidate(fixture()))
        c["after"] = [{"text": "AFTER_SENTINEL_future_secret"}]
        provider, logs = StubProvider([json.dumps(VERDICT)]), []
        with tempfile.TemporaryDirectory() as folder:
            result = apply([c], provider, {"provider": "test_fixture"}, logs, 1, 10, Path(folder), progress=None)
        message = json.dumps(provider.calls[0]["messages"])
        self.assertNotIn("AFTER_SENTINEL", message)
        self.assertNotIn("SHOW OPENING PREMISE", message)
        self.assertIn("You stole my crown", message)
        self.assertEqual(provider.calls[0]["purpose"], "cold_viewer")
        self.assertEqual(c["before_critic_judgment"], GOOD_JUDGMENT)
        self.assertEqual(c["judgment"]["clarity"], 2)
        self.assertEqual(c["judgment"]["cliffhanger"], 1)
        self.assertTrue(c["judgment"]["resolved"])
        self.assertIn("cold_viewer_resolved_ending", c["flags"])
        self.assertIn("cold_viewer_context_gap", c["flags"])
        self.assertEqual(result["reviewed"], 1)
        self.assertEqual(result["post_critic_ranked_ids"], [])
        self.assertEqual(result["rejected_reviewed_ids"], [c["id"]])
        self.assertEqual(result["final_top10_reviewed"], 0)

    def test_critic_cannot_raise_primary_judgment_scores(self):
        c = scored(candidate(fixture()))
        provider = StubProvider([json.dumps(VERDICT | {"clarity": 5, "cliffhanger": 5, "resolved": False})])
        with tempfile.TemporaryDirectory() as folder:
            apply([c], provider, {"provider": "test_fixture"}, [], 1, 10, Path(folder), progress=None)
        self.assertEqual(c["judgment"]["clarity"], GOOD_JUDGMENT["clarity"])
        self.assertEqual(c["judgment"]["cliffhanger"], GOOD_JUDGMENT["cliffhanger"])

    def test_retry_log_retains_exact_original_messages_and_cache_hits(self):
        provider, logs = StubProvider(['[]', json.dumps(VERDICT)]), []
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            apply([scored(candidate(fixture()))], provider, {"provider": "test_fixture"}, logs, 1, 10, cache, progress=None)
            self.assertEqual(logs[0]["messages"], provider.calls[0]["messages"])
            self.assertEqual(len(logs[0]["messages"]), 2)
            self.assertEqual(len(logs[1]["messages"]), 4)
            self.assertIn("validation_error", logs[0])
            apply([scored(candidate(fixture()))], provider, {"provider": "test_fixture"}, logs, 1, 10, cache, progress=None)
            self.assertEqual(len(provider.calls), 2)
            self.assertTrue(logs[-1]["cache_hit"])

    def test_two_invalid_critic_results_fail_without_fallback(self):
        provider, logs = StubProvider(['[]', '[]']), []
        c = scored(candidate(fixture()))
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError, "schema failed"):
            apply([c], provider, {"provider": "test_fixture"}, logs, 1, 10, Path(folder), progress=None)
        self.assertEqual(len(provider.calls), 2)
        self.assertNotIn("cold_viewer", c)
        self.assertEqual(c["judgment"], GOOD_JUDGMENT)

    def test_critic_refuses_offline_proxy_mode(self):
        provider = StubProvider([])
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError, "requires a real model"):
            apply([scored(candidate(fixture()))], provider, {"provider": "mock"}, [], 1, 10, Path(folder), progress=None)
        self.assertEqual(provider.calls, [])

    def test_higher_scoring_unreviewed_clip_cannot_enter_final_ranking(self):
        from test_core import SCRIPT

        class PurposeProvider:
            def complete(self, messages, purpose="judge"):
                if purpose == "judge":
                    obj = GOOD_JUDGMENT
                elif purpose == "premise":
                    obj = {"premise": 4}
                elif purpose == "cold_viewer":
                    obj = VERDICT | {"clarity": 3, "cliffhanger": 3, "resolved": False}
                else:
                    raise AssertionError(f"Unexpected model purpose {purpose}")
                return {"content": json.dumps(obj), "input_tokens": 10, "output_tokens": 20, "token_count_method": "synthetic_test_fixture"}

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "episode-001.txt"
            source.write_text(SCRIPT, encoding="utf-8")
            with patch("promo_finder.pipeline.create_provider", return_value=PurposeProvider()):
                result = run(source, root / "run", {"provider": "test_fixture"}, per_episode=2, limit=10, critic_top=1, progress=None)

        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(len(result["promos"]), 1)
        unreviewed = [c for c in result["candidates"] if "cold_viewer" not in c]
        self.assertEqual(len(unreviewed), 1)
        # The old reranking policy promoted this higher-scoring but unchecked
        # alternative after the critic lowered the first choice's scores.
        self.assertGreater(unreviewed[0]["score"]["base_score"], result["promos"][0]["score"]["base_score"])
        final_ids = [c["id"] for c in result["promos"]]
        self.assertNotIn(unreviewed[0]["id"], final_ids)
        self.assertTrue(all("cold_viewer" in c for c in result["promos"]))
        self.assertEqual(result["critic"]["ranking_policy"], "critic_reviewed_only_with_quality_floor")
        self.assertEqual(result["critic"]["post_critic_ranked_ids"], final_ids)
        self.assertEqual(result["critic"]["final_top10_reviewed"], len(result["promos"][:10]))

    def test_resolved_or_weak_ending_cannot_reach_final_recommendations(self):
        from test_core import SCRIPT

        class PurposeProvider:
            def __init__(self, verdict):
                self.verdict = verdict

            def complete(self, messages, purpose="judge"):
                obj = GOOD_JUDGMENT if purpose == "judge" else {"premise": 4} if purpose == "premise" else self.verdict
                return {"content": json.dumps(obj), "input_tokens": 10, "output_tokens": 20, "token_count_method": "synthetic_test_fixture"}

        failing_verdicts = [VERDICT | {"clarity": 3, "cliffhanger": 4, "resolved": True}, VERDICT | {"clarity": 3, "cliffhanger": 2, "resolved": False}]
        for index, verdict in enumerate(failing_verdicts):
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source = root / "episode-001.txt"
                source.write_text(SCRIPT, encoding="utf-8")
                with patch("promo_finder.pipeline.create_provider", return_value=PurposeProvider(verdict)):
                    with self.assertRaisesRegex(ValueError, "No candidate cleared"):
                        run(source, root / "run", {"provider": "test_fixture"}, per_episode=1, limit=10, critic_top=1, progress=None)
                self.assertFalse((root / "run" / "promos.json").exists())
                self.assertTrue((root / "run" / "rejected_candidates.json").is_file())
                self.assertTrue((root / "run" / "FAILED.json").is_file())


class ReviewFeedbackTests(unittest.TestCase):
    def test_primary_note_changes_only_target_candidate_messages_and_cache(self):
        first, second = candidate(fixture()), candidate(fixture(2))
        base = {"provider": "test_fixture"}
        note = "PRIMARY_NOTE_SENTINEL: verify the accusation using this clip alone."
        changed = base | {"feedback": {first["id"]: note}, "critic_feedback": {first["id"]: "CRITIC_NOTE_SENTINEL"}}
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            seed_logs = []
            seed_provider = StubProvider([json.dumps(GOOD_JUDGMENT)] * 2)
            for clip in (first, second):
                judged(clip, seed_provider, base, "Synthetic premise", cache, seed_logs)
            old_keys = {entry["candidate_id"]: entry["cache_key"] for entry in seed_logs}
            old_files = {path.name: path.read_bytes() for path in cache.glob("*.json")}
            provider, logs = StubProvider([json.dumps(GOOD_JUDGMENT)]), []
            second_copy, first_copy = deepcopy(second), deepcopy(first)
            judged(second_copy, provider, changed, "Synthetic premise", cache, logs)
            judged(first_copy, provider, changed, "Synthetic premise", cache, logs)
            self.assertTrue(logs[0]["cache_hit"])
            self.assertEqual(logs[0]["cache_key"], old_keys[second["id"]])
            self.assertFalse(logs[1]["cache_hit"])
            self.assertNotEqual(logs[1]["cache_key"], old_keys[first["id"]])
            self.assertEqual(len(provider.calls), 1)
            self.assertIn(note, provider.calls[0]["messages"][-1]["content"])
            self.assertNotIn("CRITIC_NOTE_SENTINEL", json.dumps(provider.calls[0]["messages"]))
            self.assertNotIn("PRIMARY_NOTE_SENTINEL", json.dumps(logs[0]["messages"]))
            self.assertEqual(first_copy["review_feedback"], note)
            self.assertNotIn("review_feedback", second_copy)
            for name, content in old_files.items():
                self.assertEqual((cache / name).read_bytes(), content)

    def test_critic_note_changes_only_target_candidate_messages_and_cache(self):
        clips = [scored(candidate(fixture())), scored(candidate(fixture(2)))]
        first_id, second_id = [clip["id"] for clip in clips]
        base = {"provider": "test_fixture"}
        note = "CRITIC_NOTE_SENTINEL: check whether this ending still needs an answer."
        changed = base | {"critic_feedback": {first_id: note}, "feedback": {first_id: "PRIMARY_NOTE_SENTINEL"}}
        verdict = VERDICT | {"clarity": 3, "cliffhanger": 4, "resolved": False}
        with tempfile.TemporaryDirectory() as folder:
            cache, seed_logs = Path(folder), []
            apply(deepcopy(clips), StubProvider([json.dumps(verdict)] * 2), base, seed_logs, 2, 10, cache, progress=None)
            old_keys = {entry["candidate_id"]: entry["cache_key"] for entry in seed_logs}
            old_files = {path.name: path.read_bytes() for path in cache.glob("*.json")}
            provider, logs = StubProvider([json.dumps(verdict)]), []
            new_clips = deepcopy(clips)
            apply(new_clips, provider, changed, logs, 2, 10, cache, progress=None)
            by_id = {entry["candidate_id"]: entry for entry in logs}
            self.assertFalse(by_id[first_id]["cache_hit"])
            self.assertNotEqual(by_id[first_id]["cache_key"], old_keys[first_id])
            self.assertTrue(by_id[second_id]["cache_hit"])
            self.assertEqual(by_id[second_id]["cache_key"], old_keys[second_id])
            self.assertEqual(len(provider.calls), 1)
            self.assertIn(note, provider.calls[0]["messages"][-1]["content"])
            self.assertNotIn("PRIMARY_NOTE_SENTINEL", json.dumps(provider.calls[0]["messages"]))
            self.assertNotIn("CRITIC_NOTE_SENTINEL", json.dumps(by_id[second_id]["messages"]))
            self.assertEqual(new_clips[0]["critic_review_feedback"], note)
            self.assertNotIn("critic_review_feedback", new_clips[1])
            for name, content in old_files.items():
                self.assertEqual((cache / name).read_bytes(), content)

    def test_candidate_notes_do_not_invalidate_separate_premise_cache(self):
        clip = candidate(fixture())
        base = {"provider": "test_fixture"}
        changed = base | {"feedback": {clip["id"]: "A clip review note."}, "critic_feedback": {clip["id"]: "A viewer review note."}}
        with tempfile.TemporaryDirectory() as folder:
            cache, logs = Path(folder), []
            judge_premise(clip, StubProvider(['{"premise": 4}']), base, "Synthetic premise", cache, logs)
            unused_provider = StubProvider([])
            self.assertEqual(judge_premise(clip, unused_provider, changed, "Synthetic premise", cache, logs), 4)
        self.assertEqual(unused_provider.calls, [])
        self.assertTrue(logs[1]["cache_hit"])
        self.assertEqual(logs[0]["cache_key"], logs[1]["cache_key"])

    def test_feedback_is_not_a_mechanical_guarantee_of_factual_correctness(self):
        clip = candidate(fixture())
        fabricated = GOOD_JUDGMENT | {"why": "Alice destroys an alien planet."}
        config = {"provider": "test_fixture", "feedback": {clip["id"]: "Only an accusation about a crown is shown; check the clip."}}
        provider = StubProvider([json.dumps(fabricated)])
        with tempfile.TemporaryDirectory() as folder:
            result = judged(clip, provider, config, "Synthetic premise", Path(folder), [])
        # A review note changes a prompt, not the model's reliability. This
        # synthetic non-role hallucination remains outside the literal guard.
        self.assertEqual(result["why"], fabricated["why"])
        self.assertIn(config["feedback"][clip["id"]], provider.calls[0]["messages"][-1]["content"])


if __name__ == "__main__":
    unittest.main()
