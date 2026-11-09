# Observed workload and cost projection

The main path, including recorded refinements and failed repair attempts, made **397 actual local requests**, with **272,055 input tokens and 22,000 output tokens** reported by the local inference server. That averages **5,441.1 input and 440 output tokens per episode** over 50 episodes.

Reconciliation: the initial full 4B run made 382 requests; extending critic review added 10, the literal-role repair added two, and explicit source-review feedback added three. The final report reuses those responses. Do not report its cache-only or incremental token counts as the full show workload. Raw usage files and the private evidence JSON preserve the distinction.

| Path | Per episode | Per 50-episode show | Status |
|---|---|---|---|
| Local Qwen inference API spend | $0 | $0 | Actual. Excludes hardware, power, storage and downloads. |
| Gemini free-tier token charge | $0 within eligible quota | $0 within eligible quota | Not run. Account/model quotas and data terms must be checked; no throughput promise. |
| Gemini 3.1 Pro standard projection | About $0.016 | About $0.81 | Estimate from the observed Qwen workload, not a paid API run. |

The paid projection uses $2 per million input tokens and $12 per million output tokens for prompts of at most 200k tokens: `(272055 * 2 + 22000 * 12) / 1000000 = $0.80811`. Different tokenization, reasoning tokens, retries and prompts can change the result. The prototype's calls are far shorter than 200k tokens each. Rates were checked on 5 November 2026 against [Google's official pricing](https://aistudio.google.com/docs/pricing#gemini-3.1-pro-preview); recheck before choosing an endpoint.

The original full 4B pass took 831.469 seconds on this laptop; some stress-run work overlapped, so this is not a universal latency benchmark. Cache reuse speeds later refinement. At weekly volume, run a private batch per show, cache unchanged judgments and obey the selected endpoint's quota with bounded retries. Current model execution is sequential; a production queue and per-episode summary cache remain future work.

Gemini and remote compatible adapters were tested with stubs, not live APIs. The official [rate-limit documentation](https://aistudio.google.com/docs/rate-limits) points to account-specific active limits. The submission used local inference and did not send the confidential pack to those services.
