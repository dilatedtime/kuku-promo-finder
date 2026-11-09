# Input formats

Imports are strict where guessing could create a false cut. Timestamps must be strings in `MM:SS`, `MM:SS.hh` or `HH:MM:SS.mmm` form; comma fractions are accepted for SRT. Fraction precision can be one to three digits. Values are converted to exact integer milliseconds. Decimal numeric seconds, frame-based timecodes and inferred episode numbers are rejected.

One file can be supplied directly, or a directory can contain multiple files. A directory is read recursively. Every visible file must use a supported extension, and each episode must appear once. An episode's textual header takes precedence over numbers in its filename. Distinct backend content IDs in filenames do not become episode numbers. The importer records the SHA-256 of the exact original file bytes.

## Timed TXT or Markdown

This synthetic example uses the same block structure as the supported detailed screenplay format:

```text
EPISODE NUMBER: Episode 1
EPISODE LOGLINE: A synthetic confrontation over a locked door.
CONTINUITY NOTES: Optional metadata.
--- SCRIPT START ---

SCENE 01
Scene heading: INT. HALL - DAY
Scene start: 00:00.00
Scene end: 00:25.00

Actions and dialogue:

**CAMERA:**
Start: (00:00.00) | End: (00:25.00)
Two people face a locked door.

**MARA (Urgent):**
Start: (00:00.00) | End: (00:02.00)
"Who locked us in?"

**ACTION:**
Start: (00:02.00) | End: (00:25.00)
Mara reaches for the door as footsteps approach.

--- SCRIPT END ---
```

Scene labels and Start/End fields are case-insensitive. Blank lines and unbolded speaker headers are accepted when followed by timing. `Start` and `End` can also appear on two adjacent lines. Dialogue speaker names are taken before the first parenthesis; delivery notes remain available in the original source. Camera/action/sound labels become their respective event kinds; other speaker labels become dialogue. All timed blocks need nonempty content.

The parser accepts simultaneous tracks. Their durations do not add together. Original source order is retained; retrieval sorts events by time. A warning records source blocks whose start times move backwards. A missing, malformed or backward Start/End range fails the import. A malformed explicit episode header cannot silently fall back to a filename. Multi-episode prose files must be split or converted to JSON/CSV.

## JSON

Accepts one episode object, an array of episode objects, or an object containing an `episodes` array:

```json
{
  "episodes": [
    {
      "episode": 1,
      "title": "Synthetic example",
      "logline": "A woman confronts a stranger at a locked door.",
      "continuity": "Optional context.",
      "events": [
        {"start": "00:00.00", "end": "00:02.00", "kind": "dialogue", "speaker": "MARA", "text": "Who locked us in?", "scene": "01"},
        {"start": "00:02.00", "end": "00:25.00", "kind": "action", "text": "Footsteps approach the locked door.", "scene": "01"}
      ]
    }
  ]
}
```

Required episode fields: `episode` (positive integer; `number` is also accepted) and a nonempty `events` array. Required event fields: `start`, `end`, `text`. Allowed `kind` values: `dialogue`, `action`, `camera`, `sound`; the default is `dialogue`. `speaker` and `scene` default to empty strings. The parser assigns event IDs. Event timestamps supply the candidate cut boundaries; no scene range is inferred.

## CSV

Required header columns are `episode,start,end,kind,speaker,text`; optional `scene` is accepted. Rows are grouped by episode. Standard CSV quoting supports commas, quotation marks and multiline content:

```csv
episode,start,end,kind,speaker,text,scene
1,00:00.00,00:02.00,dialogue,MARA,Who locked us in?,01
1,00:02.00,00:25.00,action,,Footsteps approach the locked door.,01
```

Each row needs a positive episode number, valid timestamps and nonempty text. An empty `kind` is invalid. Use `dialogue`, `action`, `camera` or `sound`. Extra or missing CSV cells fail explicitly. Do not include summaries or other untimed metadata as event rows.

## SRT subtitles

Use a filename such as `episode-001.srt`, `ep_2.srt` or `3.srt` so the episode number is unambiguous:

```srt
1
00:00:00,000 --> 00:00:02,000
Who locked us in?

2
00:00:20,000 --> 00:00:25,000
Someone is outside.
```

Source cue boundaries remain exact. Cues become dialogue events with unknown speakers. Subtitle-only imports carry a warning because actions, camera work and character identity may be absent. The parser does not invent visual context or fill gaps. Unsupported cue positioning metadata should be removed during explicit conversion, rather than silently ignored.

## DOCX and PDF

Install `python-docx` for DOCX and `pypdf` for PDF, or install `requirements-app.txt` for both. Documents must contain text in the timed TXT structure above. A `.docx` with tables is rejected because this importer does not establish their reading order. Export it to timed TXT, JSON or CSV first. Text PDFs are accepted with a reading-order warning. Image-only PDFs fail with an OCR/export message. OCR itself is outside this prototype.

The importer does not promise arbitrary screenplay-layout recognition. If a new show's layout differs, convert its timing explicitly to the normalized JSON/CSV schema. Do not estimate missing times to make an import succeed.

## Cut and evidence rules

- A cut is `[start, end)`, episode-relative. An event beginning exactly at the end is excluded.
- Every emitted segment boundary uses an existing scene or event timestamp. Output labels preserve source spelling, including SRT commas.
- A promo's total segment duration is 20,000-60,000 ms inclusive. Simultaneous tracks count once.
- Segment order is chronological, non-overlapping, and within the supplied episode timeline.
- No cut may split spoken dialogue. A fully timed spoken hook must finish within the first 3,000 ms.
- A hook or cliffhanger excerpt must be an exact substring of its referenced source event. Its evidence timestamps must match that event.
- Action descriptions can span cut points. Their words are not timed separately, so visual-hook impact and exact first-three-second visibility need video review.

The JSON output stores both exact `start`/`end` source labels and numeric `start_ms`/`end_ms` for segment math. Source text is untrusted story data; it never overrides the program's instructions.
