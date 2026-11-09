from __future__ import annotations

from collections import Counter
import csv
import itertools
import json
import math
from pathlib import Path
from .candidates import temporal_overlap


def wilson(successes: int, n: int) -> list[float] | None:
    if not n:
        return None
    z = 1.96
    p = successes / n
    den = 1 + z*z/n
    center = (p + z*z/(2*n)) / den
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / den
    return [round(max(0, center-half), 4), round(min(1, center+half), 4)]


def review_metrics(path: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or not {"id", "rank", "label", "reason"}.issubset(rows[0]):
        raise ValueError("Review CSV must contain id, rank, label, reason and at least one row")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate review IDs; label each sampled promo once")
    for r in rows:
        r["label"] = r["label"].strip().lower()
        if r["label"] not in {"", "good", "okay", "bad"}:
            raise ValueError(f"Invalid label for {r['id']}: {r['label']!r}; use good / okay / bad or blank")
        try:
            parsed_rank = int(r["rank"])
            if parsed_rank <= 0:
                raise ValueError("nonpositive rank")
        except ValueError:
            raise ValueError(f"Invalid rank for {r['id']}") from None
    if len({int(r["rank"]) for r in rows}) != len(rows):
        raise ValueError("Duplicate review ranks; each sampled promo needs its original unique positive rank")
    labelled = [r for r in rows if r["label"]]
    counts = Counter(r["label"] for r in labelled)
    n = len(labelled)
    top = [r for r in rows if int(r["rank"]) <= 10]
    top_labelled = [r for r in top if r["label"]]
    complete_top = {int(r["rank"]) for r in top} == set(range(1,11)) and len(top_labelled) == 10
    return {"sample_size": len(rows), "labelled": n, "unlabelled": len(rows)-n, "counts": {k: counts[k] for k in ("good", "okay", "bad")}, "strict_good_fraction": counts["good"]/n if n else None, "usable_good_or_okay_fraction": (counts["good"]+counts["okay"])/n if n else None, "strict_good_wilson_95_interval_descriptive_only": wilson(counts["good"],n), "precision_at_10_strict": sum(r["label"]=="good" for r in top_labelled)/10 if complete_top else None, "top10_labelled": len(top_labelled), "missing_reason_count": sum(not r["reason"].strip() for r in labelled), "interpretation": "No labels means no quality estimate. Top12 plus spread is not a random population sample; fractions describe this review sheet only. The Wilson interval is descriptive and does not remove selection bias. Text-only labels cannot establish video quality or ad conversion."}


def compare_runs(paths: list[Path]) -> dict:
    if len(paths) < 2:
        raise ValueError("compare needs at least two run directories")
    runs = [(p, json.loads((p/"promos.json").read_text(encoding="utf-8"))) for p in paths]
    comparisons = []
    for (pa,a),(pb,b) in itertools.combinations(runs,2):
        for k in (10,20,40):
            x,y = a["promos"][:k],b["promos"][:k]
            ix,iy = {c["id"] for c in x},{c["id"] for c in y}
            inter = len(ix & iy)
            # Greedy one-to-one relaxed match: same episode and >=80% of
            # shorter runtime overlap. Exact identity remains primary.
            options = sorted(((temporal_overlap(c,d),i,j) for i,c in enumerate(x) for j,d in enumerate(y)),reverse=True)
            usedx,usedy = set(),set()
            for overlap,i,j in options:
                if overlap >= .8 and i not in usedx and j not in usedy:
                    usedx.add(i);usedy.add(j)
            comparisons.append({"a": pa.name,"b":pb.name,"k":k,"a_count":len(x),"b_count":len(y),"exact_common":inter,"exact_jaccard":inter/len(ix|iy) if ix|iy else None,"overlap_of_smaller_top_k":inter/min(len(ix),len(iy)) if ix and iy else None,"relaxed_one_to_one_matches_80_percent":len(usedx),"same_first_pick":bool(x and y and x[0]["id"]==y[0]["id"])})
    summaries = [{"run": p.name, "judgment_mode":r["run"]["judgment_mode"],"config":r["run"]["config"],"variant":r["run"]["variant"],"retrieval":r["retrieval"],"usage":r["usage"],"ranked_count":len(r["promos"]),"episode_count":len(r["validation"]["ranked"]["episodes_represented"]),"types":r["validation"]["ranked"]["types"],"resolved_ending_flags_in_top10":sum(c["judgment"]["resolved"] for c in r["promos"][:10]),"stitched_ranked":sum(len(c["segments"])>1 for c in r["promos"])} for p,r in runs]
    return {"runs":summaries,"comparisons":comparisons,"interpretation":"Overlap measures recommendation stability, not correctness. Offline repeatability says nothing about semantic model stability. Only --fresh bypasses the judgment cache."}
