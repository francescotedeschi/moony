"""Client for the persistent MOSS Transformers inference subprocess."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

from analyzer.analyzers.moss_config import MossInferenceConfig
from analyzer.analyzers.moss_infer_core import clean_model_text


class MossPersistentSession:
    """Keep one MOSS subprocess alive and send JSON-line infer requests."""

    def __init__(self, config: MossInferenceConfig) -> None:
        self.config = config
        self._server = Path(__file__).resolve().parent / "moss_infer_server.py"
        self._proc: subprocess.Popen[str] | None = None
        self._next_id = 0
        self._stderr_lines: list[str] = []
        self._stderr_thread: threading.Thread | None = None

    def infer(self, prompt: str, audio_path: Path) -> str:
        self._ensure_started()
        assert self._proc is not None
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

        self._next_id += 1
        req_id = self._next_id
        payload = {
            "id": req_id,
            "audio": str(audio_path.resolve()),
            "prompt": prompt,
            "max_new_tokens": self.config.max_new_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "top_k": self.config.top_k,
        }
        self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

        while True:
            line = self._proc.stdout.readline()
            if not line:
                tail = "\n".join(self._stderr_lines[-40:])
                raise RuntimeError(
                    f"MOSS persistent server exited unexpectedly.\n{tail[-2000:]}"
                )
            resp = json.loads(line)
            if resp.get("id") != req_id:
                continue
            if resp.get("error"):
                raise RuntimeError(f"MOSS inference failed: {resp['error']}")
            return clean_model_text(str(resp.get("text") or ""))

    def close(self) -> None:
        proc = self._proc
        if proc is None:
            return

        self._proc = None
        try:
            if proc.stdin and proc.poll() is None:
                proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
                proc.stdin.flush()
        except OSError:
            pass

        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=2)

    def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return

        cfg = self.config
        if not cfg.repo.is_dir():
            raise FileNotFoundError(f"MOSS_MUSIC_REPO not found: {cfg.repo}")
        if not cfg.model_path.is_dir():
            raise FileNotFoundError(f"MOSS_MODEL_PATH not found: {cfg.model_path}")

        cmd = [
            cfg.python,
            str(self._server),
            "--repo",
            str(cfg.repo),
            "--model",
            str(cfg.model_path),
        ]
        env = os.environ.copy()
        if cfg.cuda_device is not None:
            env["CUDA_VISIBLE_DEVICES"] = str(cfg.cuda_device)
        ffmpeg_bin = Path(r"C:\ffmpeg\bin")
        if ffmpeg_bin.is_dir():
            env["PATH"] = str(ffmpeg_bin) + os.pathsep + env.get("PATH", "")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        env.setdefault("TQDM_DISABLE", "1")
        env.setdefault("TRANSFORMERS_VERBOSITY", "error")
        src_root = Path(__file__).resolve().parents[2]
        env["PYTHONPATH"] = str(src_root) + os.pathsep + env.get("PYTHONPATH", "")

        self._stderr_lines = []
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            cwd=str(cfg.repo),
            env=env,
        )
        self._proc = proc
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(proc,),
            daemon=True,
        )
        self._stderr_thread.start()

        assert proc.stdout is not None
        ready_line = proc.stdout.readline()
        if not ready_line:
            tail = "\n".join(self._stderr_lines[-40:])
            raise RuntimeError(f"MOSS persistent server failed to start.\n{tail[-2000:]}")
        ready = json.loads(ready_line)
        if not ready.get("ready"):
            raise RuntimeError(
                f"MOSS persistent server startup failed: {ready.get('error', ready)}"
            )

    def _drain_stderr(self, proc: subprocess.Popen[str]) -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            self._stderr_lines.append(line.rstrip())
