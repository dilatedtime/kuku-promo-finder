# Experiments and measured results

All inference on the confidential screenplay pack stayed local. The complete raw runs are in the private evidence package. These comparisons measure changes in selections and known failure modes, not precision or ad performance.

| Actual experiment | What ran | Observed result | Decision |
|---|---|---|---|
| Rule baseline | All 50 episodes; 27,994 windows; 149 retained candidates | 40 ranked clips; 26 episodes represented. An ellipsis-led revenge fragment ranked first. | Keep as a transparent plumbing baseline, not a semantic solution. |
| Baseline repeat | Same source and mechanical rules | Top 10 and all 40 ranked IDs repeat exactly. | This proves deterministic retrieval only. |
| Refined rules plus stitches | All 50 episodes; 27,342 continuous windows; 181 candidates including 31 stitches | Top 10 shares 4 exact IDs with baseline; 40 ranked clips span 34 episodes. | Keep ellipsis rejection, short-reply penalty and separate late/question retrieval routes. Retain stitches as experimental. |
| Numeric example sensitivity | Four controlled synthetic local 1.5B calls, two repeats per condition | Changing only example scores from zero to four changed all returned scores to the example values in both repeats. | Remove numeric output examples; do not assume model calibration. |
| 1.5B judgment | 150 real candidates; 150 actual local requests | 128,379 input and 16,353 output tokens. Explanations imported opening-episode facts into later clips and confused a poisoned patient. | Reject as the main judgment model; preserve errors. |
| 3B context trial | Six paired real-clip calls, with premise versus clip-only | Premise leakage remained; removing context helped one attribution, but a threat's actors were still reversed. | Isolate the premise score; do not call this a measured accuracy gain. |
| Newer 4B full run | 181 candidates; separate primary/premise calls plus critic 20 | 382 fresh actual requests; 262,924 input/20,564 output tokens; 831.469 seconds. Only 1 of its final top 10 had a critic pass because downranking promoted unchecked clips. | Fix the final ranking gate. |
| Equal critic coverage | Review the pre-ranked top 30 and only rank reviewed clips | Intermediate 30-clip output has 10/10 top-10 coverage, but 9 clips remain model-flagged resolved. | Exclude resolved outputs and require hook, cliffhanger and clarity >=3. |
| Targeted source-review feedback | Rejudge two known attribution errors; retain original responses and feedback in logs | A failed brother-to-sister repair shows the literal guard's limit. Source-review feedback produces a supported generic rationale; another critic correction removes a fabricated physical blow. | Keep candidate-specific feedback as an explicit editor/AI-assisted review step, not an invisible output edit. |
| Final review queue | Same 181 candidates; critic 30; model-based gate | 21 recommendations across 21 episodes. All 21 pass mechanical checks; all have critic review; one stitch remains. | Submit this queue and its full raw shortlist, with human labels blank. |
| Sampling stress | Separate fresh parent inference, same model, temperature 0.35/seed 29 instead of zero/11; same final gate and feedback | Final 20 clips; top 10 shares 9 IDs (Jaccard 9/11), first pick unchanged. All 20 are among the main run's 21. | Report sampling sensitivity. This is not identical-default nondeterminism or correctness. |

The final `reviewed` and `reviewed-stress` stages reuse separately generated upstream responses and make three targeted new requests each. Their incremental token totals are not the full cost per show. All cache hits are marked. The 1.5B/4B comparison changes prompts, candidate pools and critic policy too, so it cannot isolate model quality.

Ranking-only ablations hold observed judgments fixed:

- Removing type/episode diversity penalties gives six danger clips in the top 10 and three types. The final ranking has three danger clips and four types; 7/10 IDs overlap.
- Removing stitches from the same reviewed/eligible pool leaves 20 recommendations rather than 21; 9/10 top IDs overlap. It is not a full alternate retrieval run.
- Restoring pre-critic scores on the same 30 reviewed candidates shares 6/10 top IDs with the final result. This comparison includes the critic and final acceptance gate, so it is not a pure score-only causal estimate.

Three deliberately checked misses remain mixed. Retrieval now reaches the episode-3 proposal and episode-45 legal reversal, but neither reaches the final queue within the critic budget. Episode 12's ultimatum does reach the queue; its stronger 00:44.00 opening and before-response ending remain unretained. The private failure analysis gives exact evidence and seven questionable final selections.

Discarded approaches: rule scores as a final quality judgment; shared show context in the primary explanation; numeric score examples; unchecked promotion after the critic; a resolved-ending penalty without a rejection gate. Whole-episode model proposals were considered on paper, not benchmarked. Cross-episode stitch generation, pairwise ranking and a paid-model comparison were not built or run.

Gemini was considered as a remote provider, and the adapter's request and response handling passed stub tests. In a separate Antigravity check on one 22-second synthetic clip, Gemini rated clarity 4/5 versus Qwen's 3/5. Both rated the cliffhanger 5/5 and marked it unresolved. Gemini avoided Qwen's unsupported claims about the child and envelope. It added an unsupported assumption that the stranger was uninvited. The exact Gemini model and thinking level are unreported. This check uses Antigravity's agent interface. Live Gemini API integration needs a separate test. [Prompt, raw response and comparison](gemini-review.md)
