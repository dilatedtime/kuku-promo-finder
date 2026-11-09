# Reproduce the free local run

The submitted main run uses Qwen3-4B-Instruct-2507 Q4_K_M through llama.cpp on this computer's RTX 3050 with 4 GB GPU memory. It uses a loopback HTTP endpoint, not a remote API. Model files are not bundled in the public repository.

Windows, with a Vulkan-capable GPU and roughly 3 GB free disk space:

```powershell
python scripts/start_local.py --download
python -m promo_finder run --input examples/episode-001.json --output outputs/demo-4b --config configs/local-4b.json --critic-top 30 --fresh
python -m streamlit run app.py --server.address 127.0.0.1
```

Choose **Local Qwen3 4B (tested on this computer)** in the app. The helper prints a process ID and stores its local logs. It refuses to replace an existing listener. If your server is already running, skip setup and run the pipeline. The tested context is 4,096 tokens; larger contexts may exceed this GPU's memory.

The CLI command enables a fresh clip-only critic for the pre-critic top 30. Only candidates receiving that pass can enter the final ranking; unchecked alternatives remain in the raw shortlist. This can reduce the returned count below `--limit`. The critic uses the same local model and can still misread the story. Check `critic.json` for reviewed IDs and final coverage. `--fresh` bypasses caches; omit it to reuse existing judgments for identical prompts and model settings.

The helper can reuse this task's already downloaded files:

```powershell
python scripts/start_local.py --runtime-dir 'C:\path\to\existing\llama-runtime'
```

That command is specific to this computer. When the current endpoint is active, the helper deliberately reports that the port is in use; keep using the active server. To shut down after work, verify that the printed PID belongs to this local `llama-server.exe`, then stop that process.

On other systems, use the direct Transformers adapter or any locally installed OpenAI-compatible server and change only `model`/`base_url` in a config. The default Transformers example is a smaller model and was not the final main-run model. A newer model may require a newer Transformers version than the minimum needed by that example.

Pinned assets:

- [llama.cpp build b12125](https://github.com/ggml-org/llama.cpp/releases/tag/b12125), Windows Vulkan package. The helper downloads this build.
- [Official Qwen base model](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), Apache 2.0.
- [Unsloth GGUF conversion](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/tree/a06e946bb6b655725eafa393f4a9745d460374c9), pinned revision. The official 2507 GGUF repository was unavailable, so this conversion was used.
- Model file: `Qwen3-4B-Instruct-2507-Q4_K_M.gguf`, 2,497,281,120 bytes; SHA-256 `3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597`.
- Endpoint protocol: [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/tree/master/tools/server).

The setup downloads public software and weights. It does not upload screenplays. API spend for local inference is zero; power, hardware and download/storage costs are excluded. Do not compare the synthetic setup benchmark with editorial accuracy.
