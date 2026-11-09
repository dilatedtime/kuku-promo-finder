"""All output invariants are checked independently of model judgments."""
from __future__ import annotations

from collections import Counter
from .candidates import signature, speech_cut, temporal_overlap


def validate(c: dict, episodes: dict) -> dict:
    checks = {k: True for k in ("timestamp_validity", "duration_bounds", "ordering", "quote_verification", "content_coverage", "no_speech_truncation", "three_second_evidence")}
    errors = []
    total = 0
    previous = None
    for s in c.get("segments", []):
        ep = episodes.get(s.get("episode"))
        a, b = s.get("start_ms"), s.get("end_ms")
        if ep is None or type(a) is not int or type(b) is not int:
            checks["timestamp_validity"] = False
            continue
        if a not in ep.boundaries or b not in ep.boundaries:
            checks["timestamp_validity"] = False
        if not 0 <= a < b <= ep.duration:
            checks["content_coverage"] = False
        if not any(e.start < b and e.end > a for e in ep.events):
            checks["content_coverage"] = False
        if previous and (s["episode"] < previous["episode"] or (s["episode"] == previous["episode"] and a < previous["end_ms"])):
            checks["ordering"] = False
        if speech_cut(ep, a) or speech_cut(ep, b):
            checks["no_speech_truncation"] = False
        total += b - a
        previous = s
    checks["duration_bounds"] = 20000 <= total <= 60000 and total == c.get("duration_ms") and bool(c.get("segments"))
    for key, position in (("hook", 0), ("cliffhanger", -1)):
        q = c.get(key, {})
        ep = episodes.get(q.get("episode"))
        ev = next((e for e in ep.events if e.id == q.get("event_id")), None) if ep else None
        if ev is None or not q.get("quote") or q["quote"] not in ev.text or q.get("start_ms") != ev.start or q.get("end_ms") != ev.end:
            checks["quote_verification"] = False
            continue
        s = c["segments"][position]
        if ev.episode != s["episode"] or not (s["start_ms"] <= ev.start < s["end_ms"]) or ev.end > s["end_ms"]:
            checks["quote_verification"] = False
        if key == "hook":
            if ev.start >= s["start_ms"] + 3000 or (ev.kind == "dialogue" and ev.end > s["start_ms"] + 3000):
                checks["three_second_evidence"] = False
    for k, passed in checks.items():
        if not passed:
            errors.append(k)
    return {"id": c.get("id"), "passed": all(checks.values()), "checks": checks, "errors": errors}


def audit(candidates: list[dict], episodes: dict, selected: bool = False) -> dict:
    rows = [validate(c, episodes) for c in candidates]
    totals = {k: sum(r["checks"][k] for r in rows) for k in rows[0]["checks"]} if rows else {}
    duplicates = len(candidates) - len({signature(c["segments"]) for c in candidates})
    near = []
    for i, a in enumerate(candidates):
        for b in candidates[i + 1:]:
            overlap = temporal_overlap(a, b)
            if overlap >= .65:
                near.append({"a": a["id"], "b": b["id"], "fraction_of_shorter": round(overlap, 4)})
    return {"count": len(rows), "all_invariants_pass": bool(rows) and all(r["passed"] for r in rows) and duplicates == 0 and (not selected or not near), "pass_counts": totals, "pass_rates": {k: n / len(rows) for k, n in totals.items()}, "exact_duplicates": duplicates, "overlap_pairs_at_least_65_percent": near, "overlap_policy": "Shortlisted alternatives may overlap; ranked outputs suppress >=65% overlap of shorter promo.", "episodes_represented": sorted({s["episode"] for c in candidates for s in c["segments"]}), "types": dict(Counter(c.get("judgment", {}).get("type", c["retrieval_types"][0]) for c in candidates)), "failures": [r for r in rows if not r["passed"]]}
