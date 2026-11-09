# Your 21-clip review

Use the main run's `review_sheet.csv`. Save a copy as `review-labelled.csv`; keep the original blank sheet and raw outputs unchanged.

Label **all 21 final clips** in `outputs/private/reviewed/review_sheet.csv`. Allow 30-40 minutes. At roughly 90 seconds per clip, 21 reviews take 31.5 minutes. The generic sampler uses up to 24 clips; this final queue has fewer, so it includes every recommendation. If you have video, check the first three seconds and the final cut against it.

For each row, enter:

- `good`: a clear opening hook, understandable immediate stakes and a substantive unresolved ending. You would put it in an editor's shortlist.
- `okay`: useful material, but a boundary, context or spoiler issue needs work.
- `bad`: weak opening, resolved ending, confusing relationship/stakes, misleading join or a major content error.

Write one specific reason. The extra columns are blank too: `hook_within_3s`, `unresolved_end`, `standalone` and `video_checked`. You can use yes/no/uncertain there; they are for your review record and do not change the main label metric.

Run:

```powershell
python -m promo_finder review-metrics --labels outputs/private/reviewed/review-labelled.csv --output outputs/private/reviewed/editor-metrics.json
```

Strict good fraction counts only `good`. Usable fraction counts `good` and `okay`. Precision@10 appears only after all ranks 1 through 10 are labelled. A blank sheet returns null quality metrics. Do not call those nulls zero precision.

This rank-stratified sample describes the reviewed clips. It does not estimate recall over every possible promo, generalization to new shows, video quality or conversion. The statistical interval is descriptive; it does not make this a random sample.

Do not paste full clip transcripts into a public repository or public video. Share the review material only through the private assignment submission.
