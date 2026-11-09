"""Source-import contracts. Run: python -m unittest discover -s tests -v."""
import json
import tempfile
import unittest
from pathlib import Path

from promo_finder.source import SourceError, format_ms, load_pack, parse_ms, parse_text


SCRIPT = '''EPISODE NUMBER: Episode 3
EPISODE LOGLINE: A synthetic import fixture.
CONTINUITY NOTES: No confidential material.
--- SCRIPT START ---
SCENE 01
Scene heading: INT. TEST - DAY
Scene start: 00:00.00
Scene end: 00:30.00
Actions and dialogue:
**CAMERA:**
Start: (00:00.00) | End: (00:04.80)
A room with two people.
**ALICE (Angry):**
Start: (00:01.00) | End: (00:03.00)
"Who took the key?"
**ACTION:**
Start: (00:03.00) | End: (00:30.00)
Someone reaches for the door.
--- SCRIPT END ---
'''


class TimeTests(unittest.TestCase):
    def test_clock_units_are_exact(self):
        self.assertEqual(parse_ms("02:18.00"), 138000)
        self.assertEqual(parse_ms("00:00:01,025"), 1025)
        self.assertEqual(parse_ms("01:09.8"), 69800)
        self.assertEqual(format_ms(69800), "01:09.800")

    def test_invalid_clock_fails(self):
        for value in ("00:60.00", "00:99:10.000", "abc", "20", "-01:00.00", 20, "00:01.1234"):
            with self.subTest(value=value), self.assertRaises(SourceError):
                parse_ms(value)


class TextTests(unittest.TestCase):
    def test_exact_provenance_and_simultaneous_tracks(self):
        ep = parse_text(SCRIPT, "episode-003-backend999.txt")
        self.assertEqual(ep.number, 3)
        self.assertEqual(len(ep.events), 3)
        self.assertEqual(ep.events[1].speaker, "ALICE")
        self.assertEqual(ep.events[1].text, '"Who took the key?"')
        self.assertEqual(ep.events[0].kind, "camera")
        self.assertEqual(ep.boundaries[4800], "00:04.80")
        self.assertEqual(ep.duration, 30000)
        self.assertEqual(ep.events[1].start, 1000)

    def test_header_takes_precedence_over_backend_filename(self):
        ep = parse_text(SCRIPT, "episode-999-Episode-123456.txt")
        self.assertEqual(ep.number, 3)

    def test_case_and_blank_lines(self):
        variant = SCRIPT.replace("Scene start", "SCENE START").replace("Scene end", "SCENE END").replace("Start:", "START:").replace("End:", "END:").replace("**ACTION:**\n", "**ACTION:**\n\n")
        self.assertEqual(len(parse_text(variant, "script.txt").events), 3)

    def test_plain_labels_and_split_timing(self):
        variant = SCRIPT.replace("**ALICE (Angry):**", "ALICE (Angry):").replace("Start: (00:01.00) | End: (00:03.00)", "Start: 00:01.00\nEnd: 00:03.00")
        self.assertEqual(parse_text(variant, "script.txt").events[1].end, 3000)

    def test_prose_colon_does_not_drop_body_text(self):
        variant = SCRIPT.replace("Someone reaches for the door.", "Someone points at a sign:\nThe sign reads KEEP OUT.")
        ep = parse_text(variant, "script.txt")
        self.assertEqual(ep.events[-1].text, "Someone points at a sign:\nThe sign reads KEEP OUT.")

    def test_malformed_range_cannot_disappear(self):
        for replacement in ("Start: (00:01.00)", "Start: (00:01.00) | Stop: (00:03.00)", "Start: (BAD) | End: (00:03.00)"):
            with self.subTest(replacement=replacement), self.assertRaises(SourceError):
                parse_text(SCRIPT.replace("Start: (00:01.00) | End: (00:03.00)", replacement), "script.txt")

    def test_unlabelled_timing_fails(self):
        with self.assertRaisesRegex(SourceError, "unparsed"):
            parse_text(SCRIPT.replace("**ALICE (Angry):**\n", ""), "script.txt")

    def test_backwards_and_empty_blocks_fail(self):
        with self.assertRaisesRegex(SourceError, "end must follow"):
            parse_text(SCRIPT.replace("End: (00:03.00)", "End: (00:00.90)"), "script.txt")
        with self.assertRaisesRegex(SourceError, "no content"):
            parse_text(SCRIPT.replace('"Who took the key?"', ""), "script.txt")

    def test_no_episode_number_never_guessed(self):
        no_header = SCRIPT.replace("EPISODE NUMBER: Episode 3\n", "")
        with self.assertRaisesRegex(SourceError, "episode number missing"):
            parse_text(no_header, "screenplay.txt")
        self.assertEqual(parse_text(no_header, "episode-004.txt").number, 4)
        self.assertEqual(parse_text(no_header, "screenplay.txt", episode_hint=7).number, 7)

    def test_malformed_header_cannot_fall_back(self):
        with self.assertRaisesRegex(SourceError, "malformed episode"):
            parse_text(SCRIPT.replace("Episode 3", "Episode three"), "episode-003.txt")

    def test_multiple_episode_headers_fail(self):
        with self.assertRaisesRegex(SourceError, "multiple episode"):
            parse_text(SCRIPT + SCRIPT, "script.txt")


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.base / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_duplicate_episode_and_unknown_files_fail(self):
        self.write("a.txt", SCRIPT)
        self.write("b.txt", SCRIPT)
        with self.assertRaisesRegex(SourceError, "Duplicate episode"):
            load_pack(self.base)
        self.write("image.jpg", "not supported")
        with self.assertRaisesRegex(SourceError, "Unsupported files"):
            load_pack(self.base)

    def test_json_multi_episode_import(self):
        data = {"episodes": [{"episode": n, "events": [{"start": "00:00.00", "end": "00:21.00", "kind": "action", "text": "Synthetic fixture."}]} for n in (2, 1)]}
        eps = load_pack(self.write("show.json", json.dumps(data)))
        self.assertEqual([ep.number for ep in eps], [1, 2])
        self.assertEqual(eps[0].events[0].kind, "action")

    def test_json_missing_timing_and_numeric_seconds_fail_clearly(self):
        for event in ({"start": "00:00.00", "text": "x"}, {"start": 0, "end": 25, "text": "x"}):
            with self.subTest(event=event), self.assertRaises(SourceError):
                load_pack(self.write("show.json", json.dumps({"episode": 1, "events": [event]})))

    def test_csv_multiline_quotes_and_episode_grouping(self):
        text = 'episode,start,end,kind,speaker,text\n1,00:00.00,00:25.00,dialogue,Alice,"A line, with a comma.\nAnother line."\n2,00:00.00,00:20.00,action,,A test action.\n'
        eps = load_pack(self.write("show.csv", text))
        self.assertEqual(len(eps), 2)
        self.assertEqual(eps[0].events[0].text, "A line, with a comma.\nAnother line.")

    def test_empty_and_malformed_csv_fail(self):
        with self.assertRaisesRegex(SourceError, "no episodes"):
            load_pack(self.write("show.csv", "episode,start,end,kind,speaker,text\n"))
        with self.assertRaisesRegex(SourceError, "column count"):
            load_pack(self.write("show.csv", "episode,start,end,kind,speaker,text\n1,00:00.00\n"))

    def test_srt_preserves_source_comma_boundaries(self):
        text = "1\n00:00:00,000 --> 00:00:22,500\nWhere is the key?\n\n2\n00:00:23,000 --> 00:00:25,000\nI do not know.\n"
        ep = load_pack(self.write("episode-005.srt", text))[0]
        self.assertEqual(ep.boundaries[22500], "00:00:22,500")
        self.assertEqual(len(ep.events), 2)
        self.assertIn("subtitle", ep.warnings[0])
        with self.assertRaisesRegex(SourceError, "SRT episode number missing"):
            load_pack(self.write("unknown.srt", text))

    def test_non_utf8_rejected(self):
        path = self.base / "episode-001.txt"
        path.write_bytes(b"bad \xff encoding")
        with self.assertRaisesRegex(SourceError, "UTF-8"):
            load_pack(path)


if __name__ == "__main__":
    unittest.main()
