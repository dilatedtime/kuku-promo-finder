from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time

from .source import load_pack
from .candidates import generate
from .judging import judged, judge_premise, rank, recommendable, score
from .providers import create_provider
from .reporting import dump, review_sheet, write_outputs
from .validation import audit


def run(input_path, output_path, config: dict | None = None, *, variant="refined", per_episode=2, limit=40, stitches=False, fresh=False, cache_dir=None, expected_episodes=None, critic_top=0, progress=print) -> dict:
    config = dict(config or {"provider": "mock"})
    if not 1 <= per_episode <= 12 or not 1 <= limit <= 200:
        raise ValueError("per_episode must be 1..12 and limit 1..200")
    if variant not in {"baseline", "refined"}:
        raise ValueError("variant must be baseline or refined")
    started = time.monotonic()
    started_utc = datetime.now(timezone.utc).isoformat()
    episodes = load_pack(Path(input_path))
    if expected_episodes is not None and len(episodes) != expected_episodes:
        raise ValueError(f"Expected {expected_episodes} episodes but imported {len(episodes)}; no output was created.")
    eps = {e.number: e for e in episodes}
    out = Path(output_path)
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"Output directory {out} is not empty. Use a new run directory; raw runs are never overwritten.")
    out.mkdir(parents=True, exist_ok=True)
    logs = []
    try:
        provider = create_provider(config)
        candidates, retrieval = generate(episodes, variant, per_episode, stitches)
        if not candidates:
            raise ValueError("No 20-60s candidate with a source-supported first-three-second beat was found. Check timing coverage or use longer episodes; no invented fallback cuts.")
        validation = audit(candidates, eps)
        if not validation["all_invariants_pass"]:
            dump(out / "failed_validation.json", validation)
            raise ValueError("Candidate invariant checks failed. See failed_validation.json; no promos were emitted.")
        premise = " ".join(e.logline for e in episodes[:min(3, len(episodes))])[:1600]
        cache = Path(cache_dir) if cache_dir else out.parent / ".judge-cache"
        for i, c in enumerate(candidates):
            j = judged(c, provider, config, premise, cache, logs, fresh)
            if config.get("provider", "mock") != "mock" and config.get("isolate_premise", True):
                j["premise"] = judge_premise(c, provider, config, premise, cache, logs, fresh)
            c["judgment"] = j
            c["score"] = score(c, j)
            if j["resolved"] and "model_resolved_ending" not in c["flags"]:
                c["flags"].append("model_resolved_ending")
            # Persist append-only progress after each judgment. A crash or bad
            # response leaves evidence instead of an apparently successful run.
            dump(out / "model_calls.json", logs)
            if progress:
                verb = "Proxy-scored" if config.get("provider", "mock") == "mock" else "Judged"
                progress(f"{verb} {i+1}/{len(candidates)}: {c['id']} EP {c['segments'][0]['episode']} score={c['score']['base_score']:.1f}")
        critic_result = None
        if critic_top:
            if not 1 <= critic_top <= 100:
                raise ValueError("critic_top must be 1..100, or zero to disable")
            from .critic import apply
            critic_result = apply(candidates, provider, config, logs, critic_top, limit, cache, fresh, progress)
            dump(out / "model_calls.json", logs)
        rank_pool = [c for c in candidates if "cold_viewer" in c] if critic_top else candidates
        if config.get("provider", "mock") != "mock":
            rank_pool = [c for c in rank_pool if recommendable(c)]
        if not rank_pool:
            dump(out / "rejected_candidates.json", candidates)
            raise ValueError("No candidate cleared the editorial review gate (unresolved ending and hook/cliffhanger/clarity each >=3). No recommendation was invented; see rejected_candidates.json and model_calls.json.")
        promos = rank(rank_pool, limit, diversify=variant != "baseline")
        selected_check = audit(promos, eps, selected=True)
        if not selected_check["all_invariants_pass"]:
            dump(out / "failed_validation.json", selected_check)
            raise ValueError("Ranked output invariant checks failed; no final report emitted.")
        usage = {"model_requests": sum(not x["cache_hit"] for x in logs), "cache_hits": sum(x["cache_hit"] for x in logs), "input_tokens": sum(x["response"]["input_tokens"] for x in logs if not x["cache_hit"]), "output_tokens": sum(x["response"]["output_tokens"] for x in logs if not x["cache_hit"]), "token_count_methods": dict(Counter(x["response"]["token_count_method"] for x in logs if not x["cache_hit"])), "billed_api_cost_usd": 0 if config.get("provider", "mock") in {"mock", "transformers"} or str(config.get("base_url", "")).startswith(("http://127.0.0.1", "http://localhost")) else None}
        usage["billed_api_cost_usd"] = 0 if config.get("provider", "mock") in {"mock", "transformers"} or getattr(provider,"is_local_endpoint",False) else None
        manifest = [{"episode": e.number, "source_name": e.source_name, "sha256": e.source_sha256, "events": len(e.events), "boundaries": len(e.boundaries), "duration_ms": e.duration, "warnings": e.warnings, "candidates_shortlisted": retrieval["per_episode"][str(e.number)]["shortlisted"]} for e in episodes]
        result = {"run": {"version": "0.1.0", "utc_started": started_utc, "utc_completed": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": round(time.monotonic()-started, 3), "python": platform.python_version(), "judgment_mode": "offline_retrieval_proxy_NOT_LLM" if config.get("provider", "mock") == "mock" else "live_model_judgment", "config": {k: v for k,v in config.items() if k != "api_key"}, "variant": variant, "per_episode": per_episode, "limit": limit, "stitches": stitches, "fresh_requests": fresh, "prompt_sha256": hashlib.sha256(__import__('promo_finder.judging', fromlist=['SYSTEM']).SYSTEM.encode()).hexdigest(), "input_pack_fingerprint": hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()}, "source_manifest": manifest, "retrieval": retrieval, "usage": usage, "validation": {"shortlist": audit(candidates,eps), "ranked": selected_check}, "promos": promos, "candidates": candidates}
        result["run"]["critic_top"] = critic_top
        result["run"]["premise_isolated"] = config.get("isolate_premise", True) and config.get("provider", "mock") != "mock"
        result["run"]["recommendation_gate"] = "resolved=false; hook/cliffhanger/clarity >=3; critic review required when enabled" if config.get("provider","mock") != "mock" else "offline proxy; no semantic acceptance claim"
        result["run"]["input_pack_fingerprint"] = hashlib.sha256(json.dumps([{"episode":e.number,"source_name":e.source_name,"sha256":e.source_sha256} for e in episodes],sort_keys=True).encode()).hexdigest()
        # Explicit source-label fields are supplied on every segment in JSON,
        # not only on the human-readable report. Validation still uses ms.
        for c in candidates + promos:
            for s in c["segments"]:
                s["start"] = eps[s["episode"]].boundaries[s["start_ms"]]
                s["end"] = eps[s["episode"]].boundaries[s["end_ms"]]
        write_outputs(out, result, eps)
        if critic_result:
            result["critic"] = critic_result
            dump(out / "critic.json", critic_result)
            # The completed JSON includes critic provenance as well as clips.
            dump(out / "promos.json", result)
        review_sheet(out, result)
        dump(out / "validation.json", result["validation"])
        dump(out / "usage.json", usage)
        dump(out / "source_manifest.json", manifest)
        return result
    except Exception as exc:
        dump(out / "model_calls.json", logs)
        dump(out / "FAILED.json", {"error_type": type(exc).__name__, "message": str(exc), "completed": False})
        raise
