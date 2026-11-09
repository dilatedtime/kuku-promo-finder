"""Strict screenplay import, with source-boundary provenance.

Times are integer milliseconds. Input timestamps are preserved as display labels;
the parser never infers a missing timestamp, frame rate, or episode number.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class SourceError(ValueError):
    """An input cannot be imported without inventing or losing information."""


@dataclass
class Event:
    id: str
    episode: int
    scene: str
    kind: str
    speaker: str
    start: int
    end: int
    text: str
    start_label: str
    end_label: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Episode:
    number: int
    title: str
    logline: str
    continuity: str
    events: list[Event]
    boundaries: dict[int, str]
    source_name: str
    source_sha256: str
    warnings: list[str] = field(default_factory=list)

    @property
    def duration(self) -> int:
        return max(self.boundaries, default=0)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_TIMESTAMP = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$")
_RANGE = re.compile(r"^\s*Start\s*:\s*\(?([^()|]+?)\)?\s*\|\s*End\s*:\s*\(?([^()|]+?)\)?\s*$", re.I)
_HEADING = re.compile(r"^\s*(?:\*\*)?(.+?):(?:\*\*)?\s*$")
_SCENE = re.compile(r"^\s*SCENE\s+([A-Za-z0-9_-]+)\s*$", re.I)
_SCENE_TIME = re.compile(r"^\s*SCENE\s+(START|END)\s*:\s*\(?([^()]+?)\)?\s*$", re.I)
_EPISODE = re.compile(r"^\s*EPISODE\s+NUMBER\s*:\s*(?:EPISODE\s*)?(\d+)\s*$", re.I | re.M)
_HINT = re.compile(r"(?:episode|ep)[-_\s]*(\d+)", re.I)


def _starts_block(lines: list[str], index: int) -> bool:
    """Distinguish a content header from prose such as 'She says:'."""
    if not _HEADING.match(lines[index]):
        return False
    if "**" in lines[index]:
        return True
    following = index + 1
    while following < len(lines) and not lines[following].strip():
        following += 1
    return following < len(lines) and bool(re.match(r"\s*Start\s*:", lines[following], re.I))


def parse_ms(value: str) -> int:
    """Read MM:SS[.fraction] or HH:MM:SS[.fraction], never decimal seconds."""
    if not isinstance(value, str):
        raise SourceError(f"Timestamp must be a string, got {value!r}")
    match = _TIMESTAMP.fullmatch(value.strip())
    if not match:
        raise SourceError(f"Invalid timestamp {value!r}; use MM:SS.hh or HH:MM:SS.mmm")
    hours, minutes, seconds, fraction = match.groups()
    if int(seconds) >= 60 or (hours is not None and int(minutes) >= 60):
        raise SourceError(f"Invalid clock fields in timestamp {value!r}")
    return ((int(hours or 0) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int((fraction or "").ljust(3, "0") or 0)


def format_ms(ms: int) -> str:
    """Format durations/debug values. Use episode.boundaries for emitted cuts."""
    if not isinstance(ms, int) or ms < 0:
        raise SourceError(f"Milliseconds must be a nonnegative integer: {ms!r}")
    minutes, remainder = divmod(ms, 60000)
    seconds, fraction = divmod(remainder, 1000)
    return f"{minutes:02d}:{seconds:02d}.{fraction:03d}"


def _number(value: Any, source: str) -> int:
    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
        raise SourceError(f"{source}: episode number must be a positive integer, got {value!r}")
    return int(value)


def _episode_hint(source_name: str) -> int | None:
    match = _HINT.search(Path(source_name).stem)
    if match:
        return _number(match.group(1), source_name)
    stem = Path(source_name).stem
    return _number(stem, source_name) if stem.isdigit() else None


def _sha(content: str | bytes) -> str:
    return hashlib.sha256(content.encode("utf-8") if isinstance(content, str) else content).hexdigest()


def _finish(ep: Episode) -> Episode:
    if not ep.events:
        raise SourceError(f"{ep.source_name}: no timed content found; scanned PDFs need OCR before import")
    if not any(event.kind != "camera" for event in ep.events):
        ep.warnings.append("Only camera blocks found; speech/action coverage is incomplete.")
    # Source order across tracks can overlap or go backwards. Playback order is time,
    # with line order as the stable tie-break. Do not discard simultaneous tracks.
    if any(a.start > b.start for a, b in zip(ep.events, ep.events[1:])):
        ep.warnings.append("Overlapping tracks are stored in source order; candidates must sort by time.")
    seen: set[tuple[Any, ...]] = set()
    for event in ep.events:
        signature = (event.start, event.end, event.kind, event.speaker, event.text)
        if signature in seen:
            ep.warnings.append(f"Duplicate source block at line {event.line}; retained with a unique ID.")
        seen.add(signature)
    return ep


def _add_event(ep: Episode, label: str, start_label: str, end_label: str, body: str, line: int, scene: str, kind: str | None = None, speaker: str | None = None) -> None:
    if not isinstance(start_label, str) or not isinstance(end_label, str):
        raise SourceError(f"{ep.source_name}:{line}: start and end must be timestamp strings, not inferred numeric seconds")
    start_label, end_label, body = start_label.strip(), end_label.strip(), body.strip()
    try:
        start, end = parse_ms(start_label), parse_ms(end_label)
    except SourceError as exc:
        raise SourceError(f"{ep.source_name}:{line}: {exc}") from exc
    if end <= start:
        raise SourceError(f"{ep.source_name}:{line}: end must follow start ({start_label} -> {end_label})")
    if not body:
        raise SourceError(f"{ep.source_name}:{line}: timed block has no content")
    clean_label = label.strip().rstrip(":").strip()
    normalized = clean_label.upper()
    if kind is None:
        kind = {"CAMERA": "camera", "ACTION": "action", "SOUND FX": "sound", "SOUND": "sound", "SFX": "sound", "DIALOGUE": "dialogue"}.get(normalized, "dialogue")
    kind = kind.lower().strip()
    if kind not in {"camera", "action", "sound", "dialogue"}:
        raise SourceError(f"{ep.source_name}:{line}: unknown kind {kind!r}")
    if speaker is None:
        speaker = re.split(r"\s*\(", clean_label, maxsplit=1)[0].strip() if kind == "dialogue" else ""
    ep.events.append(Event(f"e{ep.number:03d}-{len(ep.events)+1:04d}", ep.number, scene, kind, speaker, start, end, body, start_label, end_label, line))
    ep.boundaries.setdefault(start, start_label)
    ep.boundaries.setdefault(end, end_label)


def parse_text(text: str, source_name: str, episode_hint: int | None = None) -> Episode:
    """Parse the pack's timed markdown blocks, also accepting plain label lines.

    Case and blank-line differences are tolerated. Missing/malformed ranges,
    unlabelled timed lines, empty blocks, and repeated headers fail explicitly.
    """
    text = text.lstrip("\ufeff")
    if "\ufffd" in text:
        raise SourceError(f"{source_name}: replacement characters found; fix the source encoding before import")
    found = _EPISODE.findall(text)
    header_count = len(re.findall(r"^\s*EPISODE\s+NUMBER\s*:", text, re.I | re.M))
    if header_count != len(found):
        raise SourceError(f"{source_name}: malformed episode number header; use 'EPISODE NUMBER: Episode 1'")
    if len(found) > 1:
        raise SourceError(f"{source_name}: multiple episode headers; split the file or use multi-episode JSON/CSV")
    number = int(found[0]) if found else episode_hint or _episode_hint(source_name)
    if number is None:
        raise SourceError(f"{source_name}: episode number missing; add 'EPISODE NUMBER: Episode 1' or name file episode-001.txt")
    number = _number(number, source_name)
    def metadata(name: str) -> str:
        match = re.search(rf"^[ \t]*{name}[ \t]*:[ \t]*(.*)$", text, re.I | re.M)
        return match.group(1).strip() if match else ""
    ep = Episode(number, metadata("EPISODE TITLE") or f"Episode {number}", metadata("EPISODE LOGLINE"), metadata("CONTINUITY NOTES"), [], {}, source_name, _sha(text))
    lines = text.splitlines()
    i, scene = 0, ""
    scene_start: tuple[int, int] | None = None
    consumed_timing: set[int] = set()
    while i < len(lines):
        raw, stripped = lines[i], lines[i].strip()
        match = _SCENE.match(raw)
        if match:
            scene = match.group(1)
            scene_start = None
            i += 1
            continue
        match = _SCENE_TIME.match(raw)
        if match:
            field_name, stamp = match.groups()
            try:
                ms = parse_ms(stamp)
            except SourceError as exc:
                raise SourceError(f"{source_name}:{i+1}: {exc}") from exc
            ep.boundaries.setdefault(ms, stamp.strip())
            if field_name.upper() == "START":
                scene_start = (ms, i+1)
            elif scene_start and ms <= scene_start[0]:
                raise SourceError(f"{source_name}:{i+1}: scene end must follow its start at line {scene_start[1]}")
            i += 1
            continue
        match = _HEADING.match(raw)
        if match and match.group(1).strip().upper() not in {"ACTIONS AND DIALOGUE", "ACTION AND DIALOGUE"}:
            label = match.group(1)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            timing = _RANGE.match(lines[j]) if j < len(lines) else None
            timing_end = j
            if not timing and j + 1 < len(lines):
                first = re.fullmatch(r"\s*Start\s*:\s*\(?([^()]+?)\)?\s*", lines[j], re.I)
                second = re.fullmatch(r"\s*End\s*:\s*\(?([^()]+?)\)?\s*", lines[j+1], re.I)
                if first and second:
                    timing = (first.group(1), second.group(1))
                    timing_end = j + 1
            if not timing:
                # A markdown content label always promises a timed block. Plain
                # metadata headings can occur before SCRIPT START, so ignore them.
                if "**" in raw:
                    raise SourceError(f"{source_name}:{i+1}: {label!r} must be followed by Start/End timestamps")
                i += 1
                continue
            starts, ends = timing.groups() if hasattr(timing, "groups") else timing
            end = timing_end + 1
            while end < len(lines):
                if _starts_block(lines, end) or _SCENE.match(lines[end]) or _SCENE_TIME.match(lines[end]) or re.match(r"\s*(?:---\s*)?SCRIPT\s+END", lines[end], re.I):
                    break
                end += 1
            _add_event(ep, label, starts, ends, "\n".join(lines[timing_end+1:end]), i+1, scene)
            consumed_timing.update(range(j, timing_end+1))
            i = end
            continue
        i += 1
    for idx, raw in enumerate(lines):
        if re.match(r"\s*(?:Start|End)\s*:", raw, re.I) and idx not in consumed_timing:
            raise SourceError(f"{source_name}:{idx+1}: unparsed/malformed timing line {raw.strip()!r}; no content was silently dropped")
        if re.match(r"\s*SCENE\s+(?:START|END)\s*:", raw, re.I) and not _SCENE_TIME.match(raw):
            raise SourceError(f"{source_name}:{idx+1}: malformed scene timestamp")
    return _finish(ep)


def _normalized_episode(data: dict[str, Any], source_name: str, digest: str) -> Episode:
    number = _number(data.get("episode", data.get("number", "")), source_name)
    ep = Episode(number, str(data.get("title", f"Episode {number}")), str(data.get("logline", "")), str(data.get("continuity", "")), [], {}, source_name, digest)
    records = data.get("events")
    if not isinstance(records, list):
        raise SourceError(f"{source_name}: episode {number} requires an events array")
    for row, record in enumerate(records, 1):
        if not isinstance(record, dict) or any(key not in record for key in ("start", "end", "text")):
            raise SourceError(f"{source_name}: event {row} requires start, end, text")
        if not isinstance(record["text"], str):
            raise SourceError(f"{source_name}: event {row} text must be a string")
        _add_event(ep, str(record.get("speaker", record.get("kind", "dialogue"))), record["start"], record["end"], record["text"], row, str(record.get("scene", "")), str(record.get("kind", "dialogue")), str(record.get("speaker", "")))
    return _finish(ep)


def _parse_json(text: str, source_name: str) -> list[Episode]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"{source_name}:{exc.lineno}: invalid JSON: {exc.msg}") from exc
    if isinstance(data, dict) and "episodes" in data:
        data = data["episodes"]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise SourceError(f"{source_name}: JSON must be an episode object, nonempty episode array, or {{'episodes': [...]}}")
    if not all(isinstance(record, dict) for record in data):
        raise SourceError(f"{source_name}: every episode must be an object")
    return [_normalized_episode(record, source_name, _sha(text)) for record in data]


def _parse_csv(text: str, source_name: str) -> list[Episode]:
    reader = csv.DictReader(io.StringIO(text))
    required = {"episode", "start", "end", "kind", "speaker", "text"}
    if not required.issubset(reader.fieldnames or []):
        raise SourceError(f"{source_name}: CSV needs columns {', '.join(sorted(required))}")
    groups: dict[int, list[dict[str, str]]] = defaultdict(list)
    for line, record in enumerate(reader, 2):
        if None in record or any(value is None for value in record.values()):
            raise SourceError(f"{source_name}:{line}: malformed CSV column count")
        groups[_number(record["episode"], f"{source_name}:{line}")].append(record)
    return [_normalized_episode({"episode": number, "events": records}, source_name, _sha(text)) for number, records in sorted(groups.items())]


def _parse_srt(text: str, source_name: str) -> Episode:
    number = _episode_hint(source_name)
    if number is None:
        raise SourceError(f"{source_name}: SRT episode number missing; name the file episode-001.srt")
    ep = Episode(number, f"Episode {number}", "", "", [], {}, source_name, _sha(text), ["SRT contains subtitle text only; visual actions and speaker identity may be absent."])
    pattern = re.compile(r"^\s*([^\n]+?)\s*-->\s*([^\n]+?)\s*$")
    blocks = re.split(r"\n\s*\n", text.strip().replace("\r\n", "\n"))
    offset = 1
    for block in blocks:
        lines = block.splitlines()
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        timing = pattern.match(lines[0]) if lines else None
        if not timing:
            raise SourceError(f"{source_name}:{offset}: malformed SRT cue")
        _add_event(ep, "DIALOGUE", *timing.groups(), "\n".join(lines[1:]), offset, "", "dialogue", "")
        offset += len(block.splitlines()) + 1
    return _finish(ep)


def load_pack(path: Path | str) -> list[Episode]:
    """Load a file or directory recursively. Every file must have a known format.

    JSON schema: {"episodes": [{"episode": 1, "events": [{"start": "00:00.00",
    "end": "00:03.00", "kind": "dialogue", "speaker": "A", "text": "..."}]}]}.
    CSV uses episode,start,end,kind,speaker,text plus optional scene.
    """
    path = Path(path)
    if not path.exists():
        raise SourceError(f"Input does not exist: {path}")
    files = sorted(path.rglob("*")) if path.is_dir() else [path]
    files = [file for file in files if file.is_file() and not file.name.startswith(".")]
    if not files:
        raise SourceError(f"No input files found: {path}")
    allowed = {".txt", ".md", ".json", ".csv", ".srt", ".docx", ".pdf"}
    unexpected = [str(file.relative_to(path) if path.is_dir() else file.name) for file in files if file.suffix.lower() not in allowed]
    if unexpected:
        raise SourceError(f"Unsupported files: {', '.join(unexpected)}. Put screenplays only in the input directory; supported: {', '.join(sorted(allowed))}")
    episodes: list[Episode] = []
    for file in files:
        suffix = file.suffix.lower()
        if suffix == ".docx":
            try:
                from docx import Document
            except ImportError as exc:
                raise SourceError("DOCX import requires 'pip install python-docx'") from exc
            doc = Document(file)
            if doc.tables:
                raise SourceError(f"{file.name}: DOCX tables are not safely ordered by this importer; export a timed TXT/JSON/CSV screenplay")
            text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
            parsed = [parse_text(text, file.name)]
        elif suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise SourceError("PDF import requires 'pip install pypdf'") from exc
            text = "\n".join(page.extract_text() or "" for page in PdfReader(file).pages)
            if not text.strip():
                raise SourceError(f"{file.name}: PDF has no extractable text; OCR or export timed TXT first")
            parsed = [parse_text(text, file.name)]
            parsed[0].warnings.append("PDF reading order can differ from page layout; inspect parsed events before trusting cuts.")
        else:
            try:
                text = file.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError as exc:
                raise SourceError(f"{file.name}: expected UTF-8 text; convert encoding explicitly before import") from exc
            parsed = _parse_json(text, file.name) if suffix == ".json" else _parse_csv(text, file.name) if suffix == ".csv" else [_parse_srt(text, file.name)] if suffix == ".srt" else [parse_text(text, file.name)]
        # Digest original bytes, including BOM/newlines; this lets a report prove
        # exactly which local input file was used.
        digest = _sha(file.read_bytes())
        for episode in parsed:
            episode.source_sha256 = digest
        episodes.extend(parsed)
    by_number: dict[int, Episode] = {}
    for episode in episodes:
        if episode.number in by_number:
            raise SourceError(f"Duplicate episode {episode.number}: {by_number[episode.number].source_name} and {episode.source_name}; put one representation of each episode in the input directory")
        by_number[episode.number] = episode
    if not episodes:
        raise SourceError(f"{path}: no episodes found; CSV/JSON inputs must contain at least one timed episode")
    return sorted(episodes, key=lambda episode: episode.number)
