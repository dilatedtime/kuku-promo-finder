from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from .judging import timeline


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def segments_text(c: dict, episodes: dict) -> str:
    return " + ".join(f"EP {s['episode']:02d} {episodes[s['episode']].boundaries[s['start_ms']]}-{episodes[s['episode']].boundaries[s['end_ms']]}" for s in c["segments"])


def csv_text(rows: list[dict], fieldnames: list[str]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def write_outputs(out: Path, result: dict, episodes: dict) -> None:
    # Called exactly once for a completed run. Raw outputs are never hand-edited.
    dump(out / "promos.json", result)
    rows = []
    for c in result["promos"]:
        rows.append({"rank": c["rank"], "id": c["id"], "segments": segments_text(c, episodes), "segments_json": json.dumps(c["segments"], ensure_ascii=False), "duration_seconds": c["duration_ms"] / 1000, "hook": c["hook"]["quote"], "cliffhanger": c["cliffhanger"]["quote"], "why": c["judgment"]["why"], "type": c["judgment"]["type"], "base_score": c["score"]["base_score"], "ranking_score": c["ranking_score"], "diversity_penalty": c["diversity_penalty"], **{k+"_score":v for k,v in c["score"]["dimensions_0_to_5"].items()}, "resolved": c["judgment"]["resolved"], "risk": c["judgment"]["risk"], "flags": "; ".join(c["flags"]), "judgment_mode": result["run"]["judgment_mode"]})
    fields = list(rows[0]) if rows else ["rank", "id"]
    (out / "promos.csv").write_text(csv_text(rows, fields), encoding="utf-8-sig", newline="")
    md = ["# Promo recommendations", "", "CONFIDENTIAL: assignment review only. Do not put this report or clip transcripts in a public repository.", "", f"Judgment mode: **{result['run']['judgment_mode']}**. All clips need video review. Scores are model opinions or labelled offline proxies, not measured advertising performance.", "", f"Read {len(episodes)} episodes; generated {result['retrieval']['generated_total']:,} continuous windows; judged {len(result['candidates'])} shortlisted candidates; ranked {len(result['promos'])} recommendations.", "", "Cuts are [start, end), episode-relative. Exact source labels are used below. Camera/action descriptions can straddle cuts; spoken lines cannot.", "", "Ranking: 28% hook, 26% cliffhanger, 20% clarity, 10% emotion, 10% premise, minus 6% spoiler; six dimensions use 0-5. Resolved ending costs 15 points, approximate visual timing costs 4. Type repetition costs up to 12; a repeated episode costs 4. Suppress >=65% overlap of shorter clip and allow at most two picks per episode.", ""]
    if result["promos"]:
        top = result["promos"][0]
        md += ["## First post to review", "", f"{top['id']} ranks first at {top['ranking_score']:.1f} points. {top['judgment']['why']} The model assigns hook {top['judgment']['hook']}/5, cliffhanger {top['judgment']['cliffhanger']}/5 and clarity {top['judgment']['clarity']}/5. Its stated weakness: {top['judgment']['risk']} This is a first editorial-review choice; conversion and retention have not been tested.", ""]
    for c in result["promos"]:
        dims = c["score"]["dimensions_0_to_5"]
        md += [f"## {c['rank']}. {c['id']} ({c['judgment']['type']})", "", f"**Segments in playback order:** {segments_text(c, episodes)}. **Total:** {c['duration_ms']/1000:.2f}s.", "", f"**Hook evidence:** {c['hook']['quote']}", "", f"**Cliffhanger evidence:** {c['cliffhanger']['quote']}", "", f"**Why:** {c['judgment']['why']}", "", f"**Scores (0-5):** " + ", ".join(f"{k}={v}" for k,v in dims.items()) + f". Base={c['score']['base_score']:.1f}; diversity penalty={c['diversity_penalty']:.1f}; ranking={c['ranking_score']:.1f}.", "", f"**Review risk:** {c['judgment']['risk']} Flags: {', '.join(c['flags']) or 'none detected by rules'}. Resolved-ending model flag: {c['judgment']['resolved']}.", ""]
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")


def review_sheet(out: Path, result: dict, count: int = 24) -> None:
    # Top 12 + 12 spread over lower ranks. Selection is deterministic and stored.
    promos = result["promos"]
    if len(promos) <= count:
        chosen = promos
    else:
        top = min(12, count)
        rest = count - top
        indices = list(range(top)) + [top + round(i * (len(promos) - top - 1) / max(1, rest - 1)) for i in range(rest)]
        chosen = [promos[i] for i in dict.fromkeys(indices)]
    rows = [{"id": c["id"], "rank": c["rank"], "segments": json.dumps(c["segments"]), "duration_seconds": c["duration_ms"] / 1000, "clip_text": timeline(c, include_camera=True), "label": "", "reason": "", "hook_within_3s": "", "unresolved_end": "", "standalone": "", "video_checked": ""} for c in chosen]
    fields = ["id", "rank", "segments", "duration_seconds", "clip_text", "label", "reason", "hook_within_3s", "unresolved_end", "standalone", "video_checked"]
    (out / "review_sheet.csv").write_text(csv_text(rows, fields), encoding="utf-8-sig", newline="")
    dump(out / "review_sample.json", {"count": len(rows), "rule": "top12 plus evenly spread lower ranks, or all if <=24", "ids": [r["id"] for r in rows], "labels_prefilled": False})
