"""Mechanical retrieval and source-boundary checks, with no model-generated times."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import re

from .source import Episode, Event


# These terms retrieve candidates. They are not a substitute for semantic review.
TERMS = {
    "betrayal": r"betray|marry|marrying|wedding|sister|mistress|abandon|divorce|affair",
    "danger": r"kill|dead|death|murder|poison|blood|knife|blade|sword|slap|strik|throat|arrest|hang|execute|attack",
    "identity": r"duke|duchess|identity|heir|secret|recogniz|recognis|reveal|crown|impostor|true name",
    "power": r"command|kneel|obey|price|tax|territory|treason|trial|accus|evidence|banish|order",
    "romance": r"husband|wife|love|kiss|bed|touch|marriage|heart|pregnan|child",
}
PATTERNS = {k: re.compile(v, re.I) for k, v in TERMS.items()}
TENSION = re.compile(r"\?|!|\.\.\.|…|how dare|you will|you must|never|stop|wait|what|who|why", re.I)
OPEN = re.compile(r"\?|\.\.\.|…|until|unless|if you|or else|about to|reaches for|raises|approach|opens|door|footstep|draws|gasps|freezes|stares|realiz", re.I)
CLOSURE = re.compile(r"thank you|all right|forgive you|i agree|it is done|it's done|at peace|falls asleep|smiles warmly|embrace|relieved|relief|resolved|safe now", re.I)


def event_dict(e: Event) -> dict:
    return asdict(e)


def intersects(e: Event, start: int, end: int) -> bool:
    return e.start < end and e.end > start


def beats(ep: Episode, start: int, end: int, kinds=None) -> list[Event]:
    return sorted((e for e in ep.events if intersects(e, start, end) and (kinds is None or e.kind in kinds)), key=lambda e: (e.start, e.end, e.id))


def speech_cut(ep: Episode, time: int) -> bool:
    return any(e.kind == "dialogue" and e.start < time < e.end for e in ep.events)


def strength(text: str) -> float:
    return sum(min(2, len(p.findall(text))) for p in PATTERNS.values()) + min(2, len(TENSION.findall(text))) * .6


def categories(text: str) -> list[str]:
    return [k for k, p in PATTERNS.items() if p.search(text)] or ["other"]


def signature(segments: list[dict]) -> str:
    raw = ";".join(f"{s['episode']}:{s['start_ms']}:{s['end_ms']}" for s in segments)
    return "P-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def excerpt(text: str, limit: int = 22) -> str:
    """Return an exact substring. No smart-quote normalization or paraphrasing."""
    words = list(re.finditer(r"\S+", text))
    return text if len(words) <= limit else text[:words[limit - 1].end()]


def make_candidate(episodes: dict[int, Episode], segments: list[dict], variant: str) -> dict | None:
    duration = sum(s["end_ms"] - s["start_ms"] for s in segments)
    if not 20000 <= duration <= 60000:
        return None
    first, last = segments[0], segments[-1]
    ep1, ep2 = episodes[first["episode"]], episodes[last["episode"]]
    opening = beats(ep1, first["start_ms"], min(first["end_ms"], first["start_ms"] + 3000), {"dialogue", "action"})
    # An entire spoken hook must fit in the first three seconds. Visual actions
    # remain approximate because a prose action is not timed word by word.
    full_open = [e for e in opening if e.start >= first["start_ms"] and e.end <= first["start_ms"] + 3000]
    usable = full_open or [e for e in opening if e.kind == "action" and e.start == first["start_ms"]]
    if not usable:
        return None
    hook = max(usable, key=lambda e: (strength(e.text), e.kind == "dialogue", -e.start))
    if variant != "baseline" and hook.kind == "dialogue" and re.match(r'^[\s\"\u201c\u201d\u2018\u2019\']*(?:\.\.\.|\u2026)', hook.text):
        return None
    endings = [e for e in beats(ep2, max(last["start_ms"], last["end_ms"] - 6000), last["end_ms"], {"dialogue", "action"}) if e.start >= last["start_ms"] and e.end <= last["end_ms"]]
    if not endings:
        return None
    cliff = max(endings, key=lambda e: (e.end, e.kind == "dialogue"))
    # Reject long dead-air tails: an unresolved beat must be near the cut.
    if last["end_ms"] - cliff.end > 2200:
        return None
    narrative = []
    transcript = []
    flags = []
    for i, s in enumerate(segments):
        ep = episodes[s["episode"]]
        if s["start_ms"] not in ep.boundaries or s["end_ms"] not in ep.boundaries:
            return None
        if speech_cut(ep, s["start_ms"]) or speech_cut(ep, s["end_ms"]):
            return None
        evs = beats(ep, s["start_ms"], s["end_ms"])
        if not evs:
            return None
        narrative += [e.text for e in evs if e.kind in {"action", "dialogue"}]
        transcript.append({"segment": i + 1, "episode": ep.number, "events": [event_dict(e) | {"partially_visible": e.start < s["start_ms"] or e.end > s["end_ms"]} for e in evs]})
    text = " ".join(narrative)
    kind = categories(hook.text + " " + cliff.text + " " + text)
    if hook.kind != "dialogue":
        flags.append("visual_hook_timing_needs_video")
    if CLOSURE.search(cliff.text):
        flags.append("possible_resolved_ending")
    if len(segments) > 1:
        flags.append("stitched_context_jump")
    # Retrieval score only; semantic scores come from the provider.
    retrieval = min(10, strength(hook.text)) * 2 + min(8, strength(cliff.text)) + (3 if OPEN.search(cliff.text) else 0) + min(3, strength(text) / 8)
    if "possible_resolved_ending" in flags and variant != "baseline":
        retrieval -= 6
    if variant != "baseline" and hook.kind == "dialogue" and len(re.findall(r"\w+", hook.text)) <= 3:
        retrieval -= 5
    after = beats(ep2, last["end_ms"], min(ep2.duration, last["end_ms"] + 10000), {"dialogue", "action"})[:5]
    before = beats(ep1, max(0, first["start_ms"] - 7000), first["start_ms"], {"dialogue", "action"})[-3:]
    return {
        "id": signature(segments), "segments": segments, "duration_ms": duration,
        "hook": {"episode": hook.episode, "event_id": hook.id, "kind": hook.kind, "quote": excerpt(hook.text), "start_ms": hook.start, "end_ms": hook.end, "fully_within_three_seconds": hook.end <= first["start_ms"] + 3000},
        "cliffhanger": {"episode": cliff.episode, "event_id": cliff.id, "kind": cliff.kind, "quote": excerpt(cliff.text), "start_ms": cliff.start, "end_ms": cliff.end},
        "retrieval_score": round(retrieval, 3), "retrieval_types": kind, "flags": flags,
        "transcript": transcript, "before": [event_dict(e) for e in before], "after": [event_dict(e) for e in after],
    }


def temporal_overlap(a: dict, b: dict) -> float:
    intersection = 0
    for x in a["segments"]:
        for y in b["segments"]:
            if x["episode"] == y["episode"]:
                intersection += max(0, min(x["end_ms"], y["end_ms"]) - max(x["start_ms"], y["start_ms"]))
    return intersection / min(a["duration_ms"], b["duration_ms"])


def generate(episodes: list[Episode], variant: str = "refined", per_episode: int = 4, stitches: bool = False) -> tuple[list[dict], dict]:
    eps = {ep.number: ep for ep in episodes}
    result = []
    counts = {}
    for ep in episodes:
        starts = sorted({e.start for e in ep.events if e.kind in {"dialogue", "action"} and not speech_cut(ep, e.start)})
        ends = sorted(t for t in ep.boundaries if not speech_cut(ep, t))
        all_candidates = {}
        for start in starts:
            for end in ends:
                if end - start < 20000:
                    continue
                if end - start > 60000:
                    break
                c = make_candidate(eps, [{"episode": ep.number, "start_ms": start, "end_ms": end}], variant)
                if c:
                    all_candidates[c["id"]] = c
        ordered = sorted(all_candidates.values(), key=lambda c: (-c["retrieval_score"], c["id"]))
        chosen = []
        pools = [("tension", ordered)]
        if variant != "baseline":
            # Preserve a route to later unresolved beats rather than letting
            # high-conflict middle-of-episode vocabulary consume every slot.
            questions = [c for c in ordered if "?" in c["cliffhanger"]["quote"]]
            tail = [c for c in ordered if c["segments"][-1]["end_ms"] >= ep.duration * .85 and OPEN.search(c["cliffhanger"]["quote"])]
            pools = [("tension", ordered), ("late_unresolved", tail), ("question_ending", questions)]
        for strategy, pool in pools:
            for c in pool:
                if all(temporal_overlap(c, old) < .72 for old in chosen):
                    c["retrieval_strategy"] = strategy
                    chosen.append(c)
                    break
            if len(chosen) >= per_episode:
                break
        for c in ordered:
            if len(chosen) >= per_episode:
                break
            if all(temporal_overlap(c, old) < .72 for old in chosen):
                c["retrieval_strategy"] = "additional_tension"
                chosen.append(c)
        counts[str(ep.number)] = {"generated": len(ordered), "shortlisted": len(chosen)}
        result += chosen
    if stitches:
        # Explore two short, chronological moments with a common named speaker.
        # A semantic judge must still decide whether the join is understandable.
        additions = []
        for ep in episodes:
            local = [c for c in result if c["segments"][0]["episode"] == ep.number]
            for a in local[:2]:
                for b in local[1:]:
                    sa, sb = a["segments"][0], b["segments"][0]
                    if sa["start_ms"] >= sb["start_ms"]:
                        continue
                    first_end = [t for t in ep.boundaries if 7000 <= t - sa["start_ms"] <= 13000 and not speech_cut(ep, t)]
                    if not first_end:
                        continue
                    ea = max(first_end)
                    if ea >= sb["start_ms"]:
                        continue
                    speakers1 = {e.speaker for e in beats(ep, sa["start_ms"], ea, {"dialogue"})}
                    speakers2 = {e.speaker for e in beats(ep, sb["start_ms"], sb["end_ms"], {"dialogue"})}
                    if not (speakers1 & speakers2):
                        continue
                    s = make_candidate(eps, [{"episode": ep.number, "start_ms": sa["start_ms"], "end_ms": ea}, sb.copy()], variant)
                    if s:
                        additions.append(s)
                        break
                if additions and additions[-1]["segments"][0]["episode"] == ep.number:
                    break
        result += additions
    return result, {"per_episode": counts, "generated_total": sum(v["generated"] for v in counts.values()), "shortlisted_total": len(result), "stitches": sum(len(c["segments"]) > 1 for c in result)}
