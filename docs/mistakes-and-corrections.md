# Mistakes and corrections

These are observed errors from this work. Model judgments are preserved in private raw runs; corrections did not overwrite them.

| Observed error | Evidence | Correction or remaining limit |
|---|---|---|
| My first inventory assumed title-case scene labels and crashed on Episode 6. | Actual IndexError during initial inspection. | Parser uses case-insensitive labels and tests the uppercase variant. |
| PDF extraction used the Windows default console encoding and failed on a job-description bullet. | Actual UnicodeEncodeError; all nine PDF pages were read after retry. | Set UTF-8 console output. |
| AI-written parser could mistake action prose ending in a colon for a speaker label. | Regression fixture reproduced body truncation. | Require timing after a plain label; keep the full action body. |
| The tiny model copied numeric score examples. | Four controlled synthetic calls changed only example scores; outputs followed zero versus four in both repeats. | Remove numeric score examples. Preserve raw synthetic experiment and treat calibration as unproven. |
| The initial 1.5B judge used excluded post-cut dialogue in its explanation and reversed which sister was rejected. | Three real-clip sanity requests, stored privately. | Remove post-cut content from primary judgment. Keep it available for editor inspection. |
| A full 1.5B run imported the opening premise into unrelated later clips and misidentified a poisoned patient. | Full 150-request run and private editorial audit. | Separate clip-only judgment from the one-field premise score; test a newer local model. This does not guarantee factual explanations. |
| The 3B model still imported opening-episode events with context present, and reversed a threat's actors in a clip-only trial. | Six paired real-clip sanity requests. | Preserve this failed approach, isolate context, and test the newer 4B model. Model attribution errors remain a review risk. |
| Baseline retrieval preferred conflict words over the later proposal or ultimatum. | Three verified missed moments in private failure analysis. | Reserve shortlist slots for late unresolved beats and question endings. Measure recovered candidates rather than claiming a precision gain. |
| Initial CSV export overwrote hook and cliffhanger text with numeric scores. | Review of the dictionary merge found colliding keys; JSON/report text remained intact. | Use separate `hook_score` and `cliffhanger_score` fields and a regression test. Old raw CSVs remain unchanged as experiment evidence. |
| Initial input fingerprint included shortlist counts, so identical source files produced different hashes after a retrieval change. | Baseline and 1.5B run fingerprints differed despite identical file hashes. | Hash only episode identity, source filename and source hash. Preserve old metadata and explain the defect. |
| Initial validator checked source event IDs and quotes but did not check hook/cliff metadata times against that event. | A forged metadata-time test passed before the fix. | Compare both metadata times to the exact referenced source event. Add regression tests. |
| Cold-viewer parser initially assumed JSON was an object; repair logs also shared a mutable prompt list. | Code review and synthetic invalid-array/repair tests. | Reject non-object JSON and create new prompt lists so original attempt logs remain unchanged. |
| Initial CLI default referenced a configuration file that did not exist. | Synthetic README command review. | Default to the shipped mock config and execute the command in a smoke test. |
| A critic pass lowered reviewed scores and promoted unchecked clips above them. | Only one of the original main run's final top 10 had received the extra review. | Make critic review a final ranking gate; retain unchecked candidates in the raw shortlist. |
| Merely penalizing resolved endings still recommended nine explicitly resolved clips in an intermediate run. | The intermediate 30-promo list included nine with `resolved=true`. | Final model recommendations require unresolved status and hook, cliffhanger and clarity scores of at least three. |
| The 4B model called a threatened husband a brother, then repaired it to sister, which was still wrong. | One of 181 initial explanations used an unsupported role. The replacement word existed elsewhere in the clip, so a literal guard accepted the wrong relationship. | Preserve both errors. Explicit source-review feedback produced a generic, supported coercion/sacrifice rationale. The narrow guard does not verify who is related to whom. |
| A cold-viewer explanation misread a verbal rebuke as a physical blow. | Private audit ties the claimed blow to an expression/reaction block in Episode 31. | Record the error and require video/editor review; do not treat model criticism as ground truth. |

A final metadata review also found that older runs captured `utc_started` after inference. Their `elapsed_seconds` and source clip times are valid, but that UTC field is effectively a completion-time snapshot. Future runs now capture UTC start before import and record completion separately. Old raw metadata was not edited.

Environment/setup failures are separate: an unused full-precision model download timed out and was cancelled; portable GPU inference replaced that path. A Streamlit smoke test needed a longer test-runner timeout. Neither establishes promo quality.

AI assistance: Codex wrote and reviewed code, tests, documents and failure analysis. Local Qwen models made the recorded judgments. The editorial audit is AI-assisted; it is not a substitute for your blank human review sheet or video checks.
