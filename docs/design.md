# Design decisions

## Three architectures considered

| Approach | Quality tradeoff | Cost | Reliability |
|---|---|---|---|
| Timed windows and tension-word retrieval | Finds obvious conflict cheaply; misses understated hooks and story meaning. | No model calls. | Repeatable and easy to validate; poor editorial calibration. |
| Model proposes complete promos from whole episodes | Flexible boundaries and joins; can overlook episodes, invent timecodes or explain events outside the clip. | Long episode prompts and possible critic calls. | Needs substantial repair and cannot be trusted with duration math. |
| Boundary enumeration, bounded retrieval, isolated model judgment | Keeps legal cuts in code and spends model work on a small shortlist. Recall is limited by retrieval. | Two short calls per candidate plus optional cold-viewer pass. | Source checks are deterministic; semantic errors remain visible in raw logs. |

The prototype uses the third approach. Continuous windows are the default. Same-episode joins are an explicit experiment. It does not try to reconstruct an edit, add music or write overlay text.

## What code owns

Import, time units, exact boundary labels, duration math, ordered segments, transcript extraction, quote matching, retrieval, overlap suppression, cache keys, weighted scores, diversity penalties, reports and metrics. The model never supplies a timestamp or a quoted hook/cliffhanger.

The source reader preserves camera, dialogue, action and sound as overlapping tracks. Segment runtime is end minus start; track runtime is never added. End boundaries are exclusive. Spoken lines may not straddle cuts. Ellipsis-led opening fragments are rejected in refined retrieval, although a legal line boundary can still be a poor sentence boundary.

## What the model owns

The primary pass sees the clip and its opening evidence, without source loglines or excluded future events. It judges the hook, unresolved ending, clarity, emotion, spoiler risk, category, rationale and weakness. A second pass receives the source opening premise and clip, but returns only a representation score. This separation was added after real context leakage in smaller models.

The optional cold-viewer pass uses a new conversation with only the clip. It summarizes who wants what and assesses clarity and resolution. It can lower scores but cannot certify a clip. It uses the same configured provider, so shared model errors are possible. When enabled, only the pre-critic top N receive the pass and can enter the final ranking. Other candidates remain in the raw shortlist. `critic.json` records the `critic_reviewed_only_with_quality_floor` policy and final coverage. Every returned clip has received the extra check; its semantic claims still need an editor's review. Candidate-specific source-review feedback is explicitly recorded when used.

## Hook and cut decisions

A spoken hook must finish within clip seconds zero through three. A strong line starting at 2.5 seconds and ending at 6 seconds does not qualify as a complete spoken hook. A visual-action block can suggest a hook, but the screenplay does not locate each sub-action within that interval; the output flags that uncertainty.

Every emitted start/end is an original source timestamp. Cuts before answers are possible because candidate ends include the preceding line's end and following line's start, provided no speech straddles the boundary. A semantic resolved-ending flag costs 15 points in scores and excludes a real-model candidate from final recommendation eligibility. This catches some closure; it does not prove every remaining ending is unresolved.

## Ranking and diversity

Six scores use zero through five. Points are `20 * (0.28*hook + 0.26*cliffhanger + 0.20*clarity + 0.10*emotion + 0.10*premise - 0.06*spoiler)`. Subtract 15 for a resolved ending and four for a visual hook whose whole action is not timed within three seconds.

Selection then subtracts 2.5 points per already-selected promo of that type, capped at 12, and four points per already-selected promo from the episode. It suppresses overlap at or above 65% of the shorter promo and allows at most two picks per episode. Final model recommendations require unresolved status and hook, cliffhanger and clarity each at least three. When the critic is enabled, only critic-reviewed candidates qualify. These are explicit starting preferences, not learned conversion weights.

With the critic enabled, the final ranking pool contains only reviewed candidates. This gate was added after a real run lowered reviewed clips and promoted unchecked alternatives. The earlier result is retained as experiment evidence. The gate trades breadth for consistent review coverage; `--critic-top 30 --limit 40` can return at most 30 promos.

## Scaling to weekly shows

Run each new show as a batch with an expected episode count and a source manifest. Cache judgments by prompt content and configuration; retries have bounded backoff for transient transport errors. A schema failure gets one repair request, then a failed-run receipt. There is no silent alternate or paid-model fallback.

Current execution is sequential at the model endpoint. A queue can run several shows on separate workers, with a worker rate limit chosen for each remote account. Per-episode parse/summary caching and distributed scheduling are future work; this prototype caches model judgments and uses source-provided loglines, rather than claiming an unbuilt summary service.

An editor reviews the top 10 against footage and approves boundaries before posting. The generic sampler uses up to 24 clips; label all 21 in the final assignment queue. Once approved and rejected examples accumulate, evaluate retrieval changes on held-out shows. Only a real ad test can measure watch-through or conversion.
