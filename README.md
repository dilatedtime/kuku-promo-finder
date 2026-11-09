# Promo Finder

Find 20-60 second promo candidates in timed screenplays. Code selects real source boundaries, checks duration and evidence, then a swappable model judges story quality. The result is an editor's review queue, with exact segments, verified hook and cliffhanger excerpts, score breakdowns and known risks.

The offline mode is a runnable plumbing baseline. Its scores are rule proxies, not model judgments or evidence of ad performance. Use a local model for story judgments. Every recommendation still needs video review.

## Start with the synthetic example

Python 3.10 or later. The basic CLI has no third-party dependencies. Run these commands from this repository's root:

```powershell
python -m promo_finder run --input examples/episode-001.json --output outputs/demo-offline --config configs/mock.json --per-episode 2 --limit 10
python -m unittest discover -s tests -v
```

These commands also work in a macOS/Linux shell with `python3` in place of `python`. Each run needs a new or empty output folder. The tool refuses to overwrite raw results. To repeat, choose `outputs/demo-offline-2`.

For an isolated environment on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-app.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

On macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-app.txt
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

The app accepts multiple uploads, displays source-labelled cuts and transcripts, and downloads JSON, CSV, a Markdown report and a blank review sheet. It allows offline and local providers only. Uploads and judgment caches use a temporary directory; generated downloads remain in session memory until cleared. File limits are 2 MB each, 25 MB total and 200 files. Keep confidential screenplays in the local app. A hosted demo should use the supplied synthetic fixture.

To use the submitted model and critic settings, select **Local Qwen3 4B (tested on this computer)** and set **Clip-only critic count** to **30**. The equivalent CLI option is `--critic-top 30`. The control defaults to zero and is disabled in offline mode. With the critic enabled, every returned promo receives the extra pass, and the app shows final review coverage. Model recommendations also require `resolved=false` and hook, cliffhanger and clarity scores of at least 3/5. The same model can still make factual mistakes. Candidate-specific review notes use the CLI configuration described below; the app does not apply private notes automatically.

## Run a new show

Put one supported representation of each episode in a private input folder. The importer recursively reads every visible file and rejects unsupported files, duplicate episodes, missing timing and malformed content. Do not mix a show's TXT and JSON exports in the same folder. See [input formats](docs/input-formats.md).

PowerShell:

```powershell
$show = 'C:\path\to\private\screenplays'
python -m promo_finder run --input "$show" --output outputs/new-show-offline --config configs/mock.json --expected-episodes 50 --per-episode 2 --limit 40
```

macOS/Linux:

```bash
python3 -m promo_finder run --input '/path/to/private/screenplays' --output outputs/new-show-offline --config configs/mock.json --expected-episodes 50 --per-episode 2 --limit 40
```

Change `--expected-episodes` to your new show's count, or omit it if the count is unknown. Count checking catches missing imports but does not prove numbering is consecutive. The source manifest records every imported episode and source-file hash. Read parser warnings before trusting cuts.

## Free local model

The submitted run used a local Qwen3 4B model through llama.cpp. Start the local server before running the CLI with `configs/local-4b.json` or selecting the 4B option in the app. Follow the [pinned local setup](docs/local-runtime.md) for a fresh Windows Vulkan setup:

```powershell
python scripts/start_local.py --download
python -m promo_finder run --input examples/episode-001.json --output outputs/demo-4b --config configs/local-4b.json --critic-top 30 --fresh
```

The optional helper downloads about 2.5 GB of public weights and a pinned runtime. It verifies the model hash and binds the server to loopback. This path was chosen because this computer's installed PyTorch is CPU-only. The smaller direct Transformers option below remains an alternative, with weaker judgments in this assignment's experiments.

```powershell
python -m pip install -r requirements-local.txt
python -m promo_finder run --input examples/episode-001.json --output outputs/demo-local --config configs/local-qwen.json --per-episode 2 --limit 10
```

The bundled configuration uses Qwen2.5-1.5B-Instruct through Transformers. The first run downloads model weights; inference sends no screenplay text to a remote service. Hardware, model downloads, electricity and storage still have costs even when API spend is zero. CPU inference may be slow. The configuration chooses CUDA if available and otherwise CPU. Change `model` to a locally available model path and `local_files_only` to `true` for a disconnected interview run. Download and test that model before the interview.

`configs/local-http.json` connects to an already running OpenAI-compatible server on `127.0.0.1:8765/v1`. Set `model` and `base_url` to your local server's values. The repository does not require that server for the offline or direct Transformers modes.

## Swap the judgment provider

All model access goes through `create_provider(config).complete(messages, purpose="judge")` in `promo_finder/providers.py`. A response contains unmodified `content`, provider/model identifiers, input/output token counts, the count method, elapsed time and raw metadata. Mechanical parsing, duration math, quote verification, deduplication and ranking stay outside providers.

Available implementations:

| Config | Provider | Credentials | Status |
| --- | --- | --- | --- |
| `mock.json` | Offline rule proxy | None | Tests plumbing; does not judge a story |
| `local-qwen.json` | Transformers, local weights | None | Free local judgment |
| `local-http.json` | OpenAI-compatible loopback server | None by default | Requires your local server |
| `local-4b.json` | Tested local Qwen3 4B server | None | Main assignment run |
| `gemini-free.json` | Gemini `generateContent` | `GEMINI_API_KEY` | Adapter provided; confirm model availability and free quota for your account |
| `openai-compatible.json` | `/chat/completions` | `PROMO_API_KEY` if configured | Use an interviewer-provided endpoint/model |

The Gemini adapter has stub coverage for request and response handling. The assignment run used local Qwen. A separate Gemini check in Antigravity compared one synthetic clip with the local cold-viewer result. [Gemini response and comparison](docs/gemini-review.md)

Remote inference starts disabled. To intentionally use an authorized remote service, copy a config to a private filename, set its model and endpoint, set `allow_remote` to `true`, and supply the key through the named environment variable. No pipeline code changes are needed. Do not put keys in JSON or commit them. The tool never substitutes a paid or alternate provider after failure. Model names, free-tier eligibility and quotas can change; an adapter's presence is not a claim that a live remote call was tested or will be free.

PowerShell, using an endpoint and model supplied to you:

```powershell
$env:PROMO_API_KEY = 'your-provided-key'
python -m promo_finder run --input examples/episode-001.json --output outputs/demo-provided-model --config configs/interview-private.json
```

Equivalent environment-variable syntax on macOS/Linux is `export PROMO_API_KEY='your-provided-key'`. `api_key_env` can be an empty string for a local server with no key. Inspect your chosen config before sending confidential material to a service. The bundled Streamlit app deliberately has no remote-provider option.

## What the pipeline does

1. Imports timestamps as integer milliseconds while preserving source labels, event IDs, line locations and file hashes. Overlapping camera, action and dialogue tracks remain distinct.
2. Enumerates continuous windows with a total duration of 20-60 seconds using real boundaries. It excludes cuts through spoken lines and requires a source-supported opening beat within three seconds. A spoken hook must finish by three seconds; visual-action timing remains approximate.
3. Shortlists candidates per episode using tension terms plus routes for late unresolved beats and question endings. Optional `--stitches` explores chronological, same-episode joins with a shared speaker. It does not generate cross-episode joins.
4. Gives only the clip and its opening evidence to the primary judge. By default, the show's premise is scored in a separate call, keeping that outside context out of the primary prompt. The primary pass scores hook, cliffhanger, clarity, emotion and spoiler risk, flags resolution, and explains one strength and one weakness. Optional `--critic-top N` sends the pre-critic top N to a fresh clip-only viewer pass that can lower clarity/cliffhanger scores and add resolution flags. All model calls use the same swappable provider. A schema failure gets one repair attempt, then fails with raw evidence preserved.
5. Uses explicit score arithmetic: 28% hook, 26% cliffhanger, 20% clarity, 10% emotion, 10% premise, minus 6% spoiler. Resolution and uncertain visual-hook timing cost points. Real-model recommendations require `resolved=false` and hook, cliffhanger and clarity scores of at least 3/5; a critic run also requires critic review. Rejected candidates stay in the raw shortlist. Ranking suppresses overlap of at least 65% of the shorter candidate, penalizes repeated types/episodes and caps picks at two per episode.
6. Validates the shortlist and final ranking independently, then writes results once. Screenplay content is evidence, never instructions to the model.

The search is bounded, not exhaustive: the model judges only the shortlist. It can miss good moments, misread dialogue, overrate a resolved scene, or assume a visual beat happens faster than it does. The optional cold-viewer pass is a separate call to the same configured provider, not a separate model or an editor label. When enabled, only the pre-critic top N receive the extra pass and can enter the final ranking. Other candidates stay in the raw shortlist. This coverage rule ensures every final recommendation received the check; it does not prove the model's account of the story is correct. No text-only system can establish acting, audio, visual impact, actual shot timing or conversion rate.

A narrow literal guard rejects a rationale's relationship words, such as brother or husband, when the same word is absent from the clip's text and speaker labels. A failed fresh or cached rationale gets a model repair request, with the original response retained in the run log. This catches some invented relationships. It does not verify who a role refers to, synonyms, or other factual claims, and it is not a semantic correctness metric.

To add the clip-only check to a real local-model run:

```powershell
python -m promo_finder run --input examples/episode-001.json --output outputs/demo-local-critic --config configs/local-qwen.json --critic-top 30
```

The default is no critic. Offline mode rejects this option because its proxies cannot perform a viewer test. With `--critic-top 30`, at most 30 recommendations can be returned even if `--limit` is 40; the model quality floor can reduce that count further. If none passes, the run fails clearly and saves rejected candidates without inventing a recommendation. A completed critic run also writes `critic.json` with checked and rejected IDs, before/after ranking, the `critic_reviewed_only_with_quality_floor` policy and actual final-top-10 coverage. These thresholds are model opinions, not measured editorial quality. Each regular candidate normally needs two real model calls, one primary and one premise-only; reviewed candidates need another call, plus any schema retries. The tested final 4B configuration is documented in [local runtime setup](docs/local-runtime.md). Set `isolate_premise` to `false` in a private config only to reproduce the earlier shared-context experiment; it sends the premise to the primary judge.

## Record a source-review correction

A private config can attach a review note to one candidate ID. For example, using synthetic IDs only:

```json
{
  "provider": "openai_compatible",
  "model": "your-local-model",
  "base_url": "http://127.0.0.1:8080/v1",
  "allow_remote": false,
  "feedback": {
    "P-synthetic-example": "Check the clip: Mara addresses a stranger; the clip does not establish a family relationship."
  },
  "critic_feedback": {
    "P-synthetic-example": "Check whether the final question remains unanswered at this cut."
  }
}
```

Use the actual ID from your private run, save the config under a private filename, and rerun into a new output folder with the same cache directory. The main `feedback` note goes only to that candidate's primary judge; `critic_feedback` goes only to its viewer check. Notes change the affected prompt and cache key. Other candidates and the separate premise score can reuse their unchanged caches. The generated JSON and raw model-call logs retain the notes and responses; earlier run folders remain unchanged. A note asks the model to recheck the source. It does not force a factual correction or count as a verified editor label. The app has no note-entry form; use the CLI for this step.

## Outputs and review

Each successful run writes:

```text
outputs/your-run/
  promos.json             # Run metadata, full shortlist and ranked promos
  promos.csv              # Ranked rows, ordered segments and score breakdowns
  report.md               # Editor-readable recommendations and first-pick rationale
  model_calls.json        # Unedited prompts/responses, retries and cache status
  source_manifest.json    # Imported episodes, hashes and parser warnings
  validation.json         # Timing, quote, duration, ordering and duplicate checks
  usage.json              # Actual provider usage or explicitly labelled estimates
  review_sheet.csv        # Clip text and blank editorial label columns
  review_sample.json      # Sampling rule and IDs
```

A failed model/validation run writes `FAILED.json` and available raw calls; it emits no successful recommendations. Before parsing succeeds, an error may occur before an output folder exists. CLI failures print `ERROR:` and return exit code 2.

Label **24 promos**, or all if fewer are generated: the top 12 plus 12 spread over lower ranks. Plan for 30-45 minutes. In `review_sheet.csv`, fill `label` with `good`, `okay` or `bad`, and write a reason. Leave the original sheet unchanged and save a labelled copy. Optional columns record opening-hook support, unresolved ending, standalone clarity and whether you checked video.

```powershell
python -m promo_finder review-metrics --labels outputs/your-run/review-labelled.csv --output outputs/your-run/editor-metrics.json
```

The script reports strict good fraction, usable good-or-okay fraction, missing reasons and precision@10 only when all top 10 are labelled. Blank sheets return null quality metrics. These describe your sampled review, not population accuracy or ad performance. The sample is deliberately stratified by rank, so its interval does not remove selection bias.

To compare fresh runs:

```powershell
python -m promo_finder run --input examples/episode-001.json --output outputs/repeat-a --config configs/local-qwen.json --fresh
python -m promo_finder run --input examples/episode-001.json --output outputs/repeat-b --config configs/local-qwen.json --fresh
python -m promo_finder compare outputs/repeat-a outputs/repeat-b --output outputs/stability.json
```

`--fresh` bypasses the judgment cache. Without it, a repeat can reuse judgments and does not test model stability. The comparison reports exact candidate overlap at 10/20/40 and relaxed one-to-one temporal overlap. Stability is separate from correctness.

The submission also runs `local-4b-stress.json`: the same local model with temperature 0.35 and seed 29 instead of temperature zero/seed 11. This is a sampling-sensitivity stress test, not proof of nondeterminism under identical default settings. The failed 1.5B experiment also used a different context policy and candidate pool, so that comparison cannot isolate model size alone.

## Keep the public repository safe

The code, configs and synthetic example can be shared. The real screenplay pack, generated transcripts, raw prompts and private reports must stay in your private submission material. `.gitignore` excludes common source/output/cache folders, but it cannot protect confidential files saved under arbitrary names. Inspect what you stage before publishing. No source screenplays or credentials are needed to run the synthetic demo.

Useful entry points: `promo_finder/source.py` for import, `candidates.py` for retrieval, `judging.py` for prompts/scoring, `validation.py` for invariants, `providers.py` for models, `pipeline.py` for batch execution and `evaluation.py` for labels/stability. Run `python -m promo_finder --help` for commands.
