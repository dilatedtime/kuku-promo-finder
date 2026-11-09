# Final request audit

The pasted request controls this work; the two supplied PDFs were read as assignment/job reference. This is a code-and-evidence audit, with a separate AI-assisted source review. It is not human editorial ground truth.

| Request | Status and evidence |
|---|---|
| Inspect the actual pack before building | Done. 50 UTF-8 TXT files, 100 scenes, 3,727 timed blocks. Source labels/case/overlapping tracks inspected; parser built from them. |
| Initial plan under 300 words, assumptions, no clarifying questions | Done in the staged chat. Assumptions are also saved in `docs/assumptions.md`. No problem questions were asked. |
| Compare at least three architectures | Done in `docs/design.md`: rules, model proposals, hybrid; quality/cost/reliability and choice stated. Proposal-only architecture was considered, not falsely claimed benchmarked. |
| Runnable GitHub-ready prototype and clear commands | Done. Stdlib CLI, packaging files, optional dependencies, synthetic fixture, pinned local-server helper, README and a public-safe ZIP. |
| Streamlit or Colab if feasible | Streamlit implemented and smoke-tested; local server health checked. No Colab notebook because the app satisfies this alternative. |
| Run again on a new show, robust formats, loud failure | TXT/MD, normalized JSON/CSV, SRT, text DOCX/PDF supported and tested. A new synthetic JSON input also completed a real local-model/critic run. Invalid/ambiguous inputs fail; no guessed timecodes. |
| Raw full-50 outputs in outputs, JSON/CSV/readable report | Done in `outputs/private/reviewed`; 21 ranked recommendations plus all 181 candidates, all 50 source manifests, model requests, CSV and report. Earlier runs retained unedited, including their documented defects. |
| Episode and every segment start/end in order | Present in JSON/CSV/report, using exact original labels and millisecond values. One final clip has two ordered segments. |
| Hook, cliffhanger and one-line reason | Source-extracted exact excerpts and model rationale included. Excerpt correctness is verified; free-form paraphrase truth is not guaranteed. Known errors and corrections are recorded. |
| Ranking and which to post first | Explicit scores/diversity; raw model rank 1 is Episode 12. AI-assisted editorial first test is rank 2, Episode 44. The solution/failure analysis explains the disagreement without editing raw ranking. |
| Max-two-page PDF-ready solution | `docs/solution.md`, `.html`, and a visually inspected two-page A4 PDF. It covers choice, assumptions, method, scale/cost, human review, evidence, failures and AI use. |
| Real mistakes log | `docs/mistakes-and-corrections.md` records observed parsing, model, ranking, cache/provenance and export errors. Failed attempts remain raw. |
| Three-minute walkthrough | `docs/walkthrough.md`, 362 spoken words with timed screen actions. Recording in your own voice remains your action. |
| Free version, no paid API requirement | Local Qwen plus offline mode. Actual inference API spend $0; hardware/power/download costs excluded. No remote service received screenplay text. |
| Swappable model behind one interface | `create_provider(config).complete(...)`; mock, Transformers, compatible HTTP and Gemini. Actual model swaps were local. Remote adapters used stubs, not live APIs; direct Transformers inference was not completed here. |
| Never invent start/end timestamps | Code generates source-boundary cuts; independent validation reloaded original sources. 21/21 final and 20/20 stress pass. |
| Every promo 20-60 seconds, summed segments | Enforced in generator and independent validation, including exact 20/60-second tests. 21/21 final pass. |
| Ordered, non-overlapping real segments | Episode/time order, self-overlap, source range/content and no speech truncation checked. Final 21/21 pass. |
| Exact hook/cliff quotes from source | Event identity, excerpt substring, source timing and segment inclusion checked. Final 21/21 pass; CSV matches JSON. |
| No fabricated show content | Exact cuts/excerpts are protected. Semantic rationale/critic errors cannot be fully excluded. Two known attribution texts were regenerated with explicit AI-assisted source notes; other questionable interpretations remain in the failure report. This requirement is not a blanket factuality guarantee. |
| Code does mechanical work; LLM judges | Parser, timing, retrieval, quote checks, score arithmetic, dedup, cache, reports and metrics are code. Models judge story criteria. Offline proxy scores are labelled and not presented as semantic evaluation. |
| Experiments and discarded ideas | Actual baseline/repeat/refined/stitch, model/context trials, score-example test, critic/gate, feedback and sampling stress. `docs/experiments.md` separates measured selection changes from hypotheses. |
| Concrete first-three-second test | Complete spoken hook must finish by three seconds; visual action timing flagged/limited. Mechanical support is not proof the hook stops a viewer. |
| Cliff cut before answer and resolved checks | End-exclusive cuts, speech protection, model resolution flags and final rejection gate. Real weak reaction/clause/vow endings still occur and are documented. |
| Explicit ranking criteria and breakdown | Hook/cliff/clarity/emotion/premise/spoiler plus type/episode diversity and overlap suppression. Values and weighted contributions appear per clip. |
| Small review CSV, blank user labels/reasons | Exactly 21 final rows, all six user-check columns blank. Label all 21, roughly 30-40 minutes. |
| Precision-style script after labels | Implemented and tested. Current blank-sheet metrics are null; no editorial precision claimed. Human labels remain pending. |
| Automated checks on all outputs and diversity | `outputs/private/evaluation/evidence.json` aggregates every run. Final shortlist 181/181 and selections 21/21 pass; no final duplicates/near overlaps; top 10 has four types. Overlapping raw alternatives are intentional and reported. |
| More than one run and measured stability | Separate fresh parent runs introduce model/sampling variation; final matched-policy artifacts share 9/10 top IDs, same first pick. Final refinements reuse marked caches. Sampling stress is not identical-default nondeterminism. |
| Different model if possible | Actual 1.5B full run, paired 3B sanity, 4B full run. Prompts/policies/pools differ, so this does not isolate a model-only accuracy effect. |
| At least five real questionable picks and why chosen | Seven current final IDs with exact boundaries, source evidence, cause and suggested checks in private `evaluation/failure-analysis.md`. These are AI-assisted judgments, not prefilled human bad labels. |
| Good missed moments; cheap fixes and before/after | Three checked hypotheses. Late routes recover proposal/ultimatum/legal-reversal material; only the ultimatum reaches the final ranking. More direct boundaries remain missed. Ellipsis, critic coverage, resolved gate and attribution fixes are measured. |
| State what text cannot know | Acting, sound, exact visual/sub-action timing, frame rate, shot impact, conversion and audience response are explicitly limited. |
| Actual tokens/cost per episode/show; paid estimate | 397 actual main-path requests, 272,055 input/22,000 output; means 5,441.1/440 per episode. $0 local API; about $0.81/show paid projection with official price link and tokenization/reasoning caveats. |
| Weekly batch, caching, retries, editor points | Batch/source hashes/judgment cache/bounded retries implemented; top-10 footage review and boundary approval stated. Distributed queue and per-episode summary caching remain future work. |
| Staged updates, samples, real runnable code/tested claims | Staged chat updates included source inspection, baseline counts, model errors, exact real clip and refinements. 79 tests pass; app smoke and new-input local run completed. |
| Repo tree, commands, doc/log/script/user actions | `START_HERE.md`, README, linked documents and final handoff. No public repo or hosted service was published automatically. |
| Confidentiality | Public-safe ZIP inspected to exclude screenplays, transcripts, real prompts, private feedback configs and private outputs. Private results bundle stays separate. |

Remaining limits and user actions:

- Human labels, footage checks, a real ad test, your recording and form submission are unfinished. No precision or conversion number can be supplied before those steps.
- Remote Gemini/paid APIs are not live-tested, and the direct Transformers path was not run successfully here. The tested free path is the local compatible GPU server.
- No cross-episode stitch generator, pairwise ranking, full character bible, OCR/unknown-layout conversion, production queue or summary cache was built. These optional ideas are disclosed, not claimed complete.
- The current shortlist and critic budget miss good material. Model prose can still misinterpret a clip. The known failure report remains part of the submission.
- No separate Writing-Rules document or writing samples were present among the supplied files. The explicit style instructions in chat were followed; unseen documents were not claimed reviewed.
