"""Local Streamlit review UI. Run: streamlit run app.py --server.address 127.0.0.1."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

from promo_finder.judging import timeline
from promo_finder.pipeline import run


ROOT = Path(__file__).resolve().parent
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
EXTENSIONS = {".txt", ".md", ".json", ".csv", ".srt", ".docx", ".pdf"}
DOWNLOADS = {
    "promos.json": "application/json",
    "promos.csv": "text/csv",
    "report.md": "text/markdown",
    "review_sheet.csv": "text/csv",
    "validation.json": "application/json",
    "usage.json": "application/json",
}
MODES = {
    "Offline plumbing demo (no model judgment)": "mock.json",
    "Local Qwen3 4B (tested on this computer)": "local-4b.json",
    "Free local Qwen model": "local-qwen.json",
    "Local compatible HTTP server": "local-http.json",
}


def validate_uploads(files: list[tuple[str, bytes]]) -> None:
    """Reject collisions and traversal before writing any uploaded file."""
    if not files:
        raise ValueError("Choose at least one screenplay file.")
    if len(files) > 200:
        raise ValueError("Choose at most 200 screenplay files per run.")
    seen = set()
    total = 0
    for name, content in files:
        if not name or name.startswith(".") or any(c in name for c in ("/", "\\", ":", "\x00")):
            raise ValueError(f"Unsafe file name {name!r}. Use a plain file name such as episode-001.txt.")
        if name.casefold() in seen:
            raise ValueError(f"Duplicate uploaded file name {name!r}; each file needs a unique name.")
        seen.add(name.casefold())
        if Path(name).suffix.lower() not in EXTENSIONS:
            raise ValueError(f"Unsupported file {name!r}. Use TXT, MD, JSON, CSV, SRT, DOCX or PDF.")
        if not content:
            raise ValueError(f"File {name!r} is empty.")
        if len(content) > MAX_FILE_BYTES:
            raise ValueError(f"File {name!r} exceeds the 2 MB limit.")
        total += len(content)
    if total > MAX_TOTAL_BYTES:
        raise ValueError("The selected files exceed 25 MB in total. Split this input into smaller packs.")


def execute_uploads(files: list[tuple[str, bytes]], config: dict, *, per_episode: int, limit: int, stitches: bool, expected_episodes: int | None, critic_top: int = 0, progress=None) -> tuple[dict, dict[str, bytes]]:
    """All input, generated files and judgment caches live in one temporary tree.

    Return owned bytes so downloads still work after the tree is removed. Do not
    store temporary file paths in Streamlit session state.
    """
    validate_uploads(files)
    if config.get("provider") not in {"mock", "transformers", "openai_compatible"} or config.get("allow_remote") is not False:
        raise ValueError("The review app accepts bundled offline/local configurations only. Use the CLI for an intentional remote-provider run.")
    # The offline mode cannot perform a viewer judgment, including when this
    # helper is called directly rather than through the disabled sidebar field.
    if config.get("provider") == "mock":
        critic_top = 0
    with tempfile.TemporaryDirectory(prefix="promo-finder-") as folder:
        scratch = Path(folder)
        source = scratch / "input"
        source.mkdir()
        for name, content in files:
            (source / name).write_bytes(content)
        output = scratch / "run"
        result = run(source, output, config, variant="refined", per_episode=per_episode, limit=limit, stitches=stitches, fresh=True, cache_dir=scratch / "cache", expected_episodes=expected_episodes, critic_top=critic_top, progress=progress)
        downloads = {name: (output / name).read_bytes() for name in DOWNLOADS}
    return result, downloads


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Promo Finder", layout="wide")
    st.title("Promo Finder")
    st.write("Find source-grounded, 20–60 second promo candidates. Review exact cuts, story scores and risks before checking them against video.")
    st.caption("Run this app on your computer for confidential screenplays. Use synthetic inputs in hosted demos. Inputs, outputs and model responses are removed from temporary storage after each run; results remain in this browser session until you clear them.")

    with st.sidebar:
        st.header("Run settings")
        mode = st.selectbox("Judgment mode", list(MODES))
        config_path = ROOT / "configs" / MODES[mode]
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            st.error(f"Cannot read bundled configuration: {exc}")
            st.stop()
        if config.get("provider") == "mock":
            st.warning("Offline mode tests parsing, timing and output generation. Its scores are rule proxies. It cannot judge whether a promo works.")
        elif config.get("provider") == "transformers":
            st.info("The model runs locally. The first run may download free model weights and can take several minutes. Install requirements-local.txt first.")
            st.caption(f"Model: {config.get('model')}")
        else:
            st.info("Start the local compatible model server before running. Screenplay text goes to the loopback endpoint in the bundled configuration.")
            st.caption(f"Endpoint: {config.get('base_url')}")
        per_episode = st.slider("Candidates to judge per episode", 1, 6, 2)
        limit = st.slider("Maximum ranked promos", 1, 100, 40)
        if config.get("provider") == "mock":
            st.slider("Clip-only critic count (0 = off)", 0, 40, 0, disabled=True, key="critic_offline")
            critic_top = 0
        else:
            critic_top = st.slider("Clip-only critic count (0 = off)", 0, 40, 0, key="critic_local", help="When enabled, only candidates receiving this extra check can enter the final ranking. Use 30 for the submitted final configuration.")
        st.caption("A critic uses another call to the same local model. It checks story clarity and the ending; its conclusions still need editorial review.")
        stitches = st.checkbox("Explore same-episode stitched clips", value=False)
        expected = st.number_input("Expected episode count (0 = any)", min_value=0, max_value=500, value=0, step=1)
        st.caption("Import fails if a required timestamp or episode number is missing. SRT provides subtitles without reliable visual context. PDF import needs extractable text; DOCX tables require a TXT/JSON/CSV export.")
        if st.button("Clear saved results"):
            st.session_state.pop("promo_result", None)
            st.session_state.pop("promo_downloads", None)

    uploaded = st.file_uploader("Screenplay files", type=[x.lstrip(".") for x in sorted(EXTENSIONS)], accept_multiple_files=True, help="You can select all 50 episode files at once. Limit: 2 MB per file and 25 MB total.")
    st.caption("Use one representation per episode. Episode headers take precedence over backend IDs in file names. For SRT, name files episode-001.srt, episode-002.srt, and so on.")

    if st.button("Find promos", type="primary", disabled=not uploaded):
        # Clear previous run first so a failure cannot leave old results looking
        # like the output of the new input.
        st.session_state.pop("promo_result", None)
        st.session_state.pop("promo_downloads", None)
        status = st.empty()
        try:
            files = [(item.name, item.getvalue()) for item in uploaded]
            with st.spinner("Importing, validating and judging candidates..."):
                result, downloads = execute_uploads(files, config, per_episode=per_episode, limit=limit, stitches=stitches, expected_episodes=int(expected) or None, critic_top=critic_top, progress=status.info)
            st.session_state["promo_result"] = result
            st.session_state["promo_downloads"] = downloads
            status.success(f"Completed: {len(result['source_manifest'])} episodes, {len(result['candidates'])} candidates, {len(result['promos'])} ranked promos.")
        except Exception as exc:
            status.empty()
            st.error(f"Run failed ({type(exc).__name__}): {exc}")
            st.info("No partial recommendations were saved. Correct the input or model setup and run again. For persistent failure logs, use the CLI with a private output directory.")

    result = st.session_state.get("promo_result")
    if result is None:
        st.write("Upload your timed screenplay files, choose a judgment mode, then select **Find promos**. For a quick check, use the synthetic example in the repository.")
        return
    st.subheader("Ranked recommendations")
    mode_label = result["run"]["judgment_mode"]
    st.caption(f"Judgment mode: {mode_label}. Every recommendation needs editorial and video review. Scores do not measure ad performance.")
    if result.get("critic"):
        st.caption(f"Clip-only critic checked {result['critic']['reviewed']} candidates. Final ranking includes reviewed candidates only; {result['critic']['final_top10_reviewed']} of the returned top {min(10, len(result['promos']))} received the pass.")
    left, middle, right = st.columns(3)
    left.metric("Episodes imported", len(result["source_manifest"]))
    middle.metric("Ranked promos", len(result["promos"]))
    right.metric("Invariant checks", "PASS" if result["validation"]["ranked"]["all_invariants_pass"] else "FAIL")
    rows = []
    for promo in result["promos"]:
        segment_text = " + ".join(f"EP {segment['episode']} {segment['start']} – {segment['end']}" for segment in promo["segments"])
        rows.append({"Rank": promo["rank"], "ID": promo["id"], "Segments in order": segment_text, "Seconds": promo["duration_ms"] / 1000, "Type": promo["judgment"]["type"], "Rank score": promo["ranking_score"], "Hook /5": promo["judgment"]["hook"], "Cliffhanger /5": promo["judgment"]["cliffhanger"], "Clarity /5": promo["judgment"]["clarity"], "Resolved ending": promo["judgment"]["resolved"]})
    st.dataframe(rows, width="stretch", hide_index=True)
    st.subheader("Download this run")
    columns = st.columns(3)
    for index, (name, mime) in enumerate(DOWNLOADS.items()):
        columns[index % 3].download_button(name, st.session_state["promo_downloads"][name], file_name=name, mime=mime, key=f"download_{name}")
    st.caption("The review sheet leaves all editorial label columns blank. Keep downloaded reports and clip text in your private assignment package.")
    for promo in result["promos"]:
        with st.expander(f"{promo['rank']}. {promo['id']} · {promo['duration_ms']/1000:.2f}s · {promo['judgment']['type']}"):
            for index, segment in enumerate(promo["segments"], 1):
                st.write(f"Segment {index}: Episode {segment['episode']}, {segment['start']} to {segment['end']} (end excluded).")
            st.write("**Hook evidence:**", promo["hook"]["quote"])
            st.write("**Cliffhanger evidence:**", promo["cliffhanger"]["quote"])
            st.write("**Why:**", promo["judgment"]["why"])
            st.write("**Review risk:**", promo["judgment"]["risk"])
            st.write("**Flags:**", ", ".join(promo["flags"]) or "None detected by rules")
            if "cold_viewer" in promo:
                st.write("**Clip-only viewer summary:**", promo["cold_viewer"]["summary"])
                st.write("**Viewer-check risk:**", promo["cold_viewer"]["risk"])
            st.json({"scores_0_to_5": promo["score"]["dimensions_0_to_5"], "weighted_points": promo["score"]["weighted_points"], "boundary_and_resolution_penalty": promo["score"]["resolved_and_timing_penalty"], "diversity_penalty": promo["diversity_penalty"], "rank_score": promo["ranking_score"]})
            st.code(timeline(promo, include_camera=True), language=None)
    with st.expander("Source coverage and automated checks"):
        st.dataframe(result["source_manifest"], width="stretch", hide_index=True)
        st.json(result["validation"])


if __name__ == "__main__":
    main()
