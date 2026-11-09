"""Optional pinned Windows Vulkan setup. Downloads public weights, never scripts.

python scripts/start_local.py --download
python scripts/start_local.py --runtime-dir C:/path/to/existing/llama-runtime
Use Ctrl+C in your client or stop the printed PID when finished.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile

MODEL = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
MODEL_URL = "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/a06e946bb6b655725eafa393f4a9745d460374c9/" + MODEL
MODEL_SHA = "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597"
RUNTIME_URL = "https://github.com/ggml-org/llama.cpp/releases/download/b12125/llama-b12125-bin-win-vulkan-x64.zip"


def download(url: str, target: Path) -> None:
    part = target.with_suffix(target.suffix + ".part")
    print(f"Downloading public asset: {target.name}", flush=True)
    # No authentication, inference or private file upload takes place here.
    with urllib.request.urlopen(url, timeout=120) as response, part.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    part.replace(target)


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime-dir",type=Path,default=Path("work/local-runtime"))
    p.add_argument("--download",action="store_true",help="Download ~2.5GB model and ~38MB Windows runtime if absent")
    p.add_argument("--device",default="auto",help="auto prefers listed NVIDIA device; explicit example Vulkan1")
    p.add_argument("--port",type=int,default=8765)
    a=p.parse_args()
    if platform.system()!="Windows":
        raise ValueError("This optional helper is for Windows. Use a local OpenAI-compatible server or Transformers on other systems; see README.")
    root=a.runtime_dir.resolve();root.mkdir(parents=True,exist_ok=True)
    server=root/"bin"/"llama-server.exe";model=root/MODEL
    if not server.exists() or not model.exists():
        if not a.download:
            raise ValueError("Model/runtime missing. Run again with --download, or point --runtime-dir to an existing setup.")
        if not server.exists():
            archive=root/"runtime.zip";download(RUNTIME_URL,archive)
            (root/"bin").mkdir(exist_ok=True)
            with zipfile.ZipFile(archive) as z:
                for member in z.infolist():
                    resolved=(root/"bin"/member.filename).resolve()
                    if not resolved.is_relative_to((root/"bin").resolve()):
                        raise ValueError("Unsafe path in runtime archive")
                z.extractall(root/"bin")
        if not model.exists():
            download(MODEL_URL,model)
    digest=None
    if sys.version_info>=(3,11):
        with model.open("rb") as stream:
            digest=hashlib.file_digest(stream,"sha256").hexdigest()
    if digest is None:
        h=hashlib.sha256()
        with model.open("rb") as f:
            while chunk:=f.read(1024*1024):h.update(chunk)
        digest=h.hexdigest()
    if digest!=MODEL_SHA:
        raise ValueError("Model SHA-256 mismatch. Do not start; verify/download the pinned file again.")
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1",a.port))==0:
            raise ValueError(f"Port {a.port} already has a listener. Keep the existing server or stop its verified PID; this helper will not replace it.")
    device=a.device
    if device=="auto":
        found=subprocess.run([str(server),"--list-devices"],capture_output=True,text=True,check=True)
        lines=(found.stdout+found.stderr).splitlines()
        vulkan=[line for line in lines if re.search(r"Vulkan\d+:",line)]
        preferred=next((line for line in vulkan if "NVIDIA" in line.upper()),vulkan[-1] if vulkan else "")
        match=re.search(r"Vulkan\d+",preferred)
        if not match:
            raise ValueError("No Vulkan GPU found. Use Transformers CPU mode, or an explicit compatible server.")
        device=match.group()
    command=[str(server),"-m",str(model),"--device",device,"-ngl","99","-c","4096","-np","1","--host","127.0.0.1","--port",str(a.port),"--alias","qwen3-4b-local","-t","6"]
    with (root/"server.stdout.log").open("w") as out,(root/"server.stderr.log").open("w") as err:
        process=subprocess.Popen(command,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    (root/"server.pid").write_text(str(process.pid),encoding="ascii")
    print(f"Started PID {process.pid}, {device}; waiting for local health...",flush=True)
    for _ in range(60):
        if process.poll() is not None:
            raise ValueError(f"Server exited. Read {root/'server.stderr.log'}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{a.port}/health",timeout=2) as response:
                if json.load(response).get("status")=="ok":
                    print(f"Ready: http://127.0.0.1:{a.port}/v1; use configs/local-4b.json. PID {process.pid}")
                    return 0
        except OSError:
            pass
        time.sleep(1)
    raise ValueError(f"Server did not become ready in 60s. Inspect logs at {root}; PID {process.pid} may still be loading.")


if __name__=="__main__":
    try:raise SystemExit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr);raise SystemExit(2)
