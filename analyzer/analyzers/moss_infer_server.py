"""
Persistent MOSS-Music inference server (Transformers path).

Loads the model once, then serves JSON-line requests on stdin until shutdown.
Stdout carries only JSON responses so a parent process can reuse the same weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    import os

    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TQDM_DISABLE", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    model_path = Path(args.model).resolve()

    try:
        from analyzer.analyzers.moss_infer_core import infer_moss, load_moss_model

        processor, model = load_moss_model(repo, model_path)
    except Exception as exc:
        _emit({"ready": False, "error": str(exc)})
        return 1

    _emit({"ready": True})

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            _emit({"error": f"invalid json: {exc}"})
            continue

        cmd = req.get("cmd")
        if cmd == "shutdown":
            _emit({"ok": True})
            return 0

        req_id = req.get("id")
        try:
            text = infer_moss(
                processor,
                model,
                audio_path=str(req["audio"]),
                prompt=str(req["prompt"]),
                max_new_tokens=int(req.get("max_new_tokens", 1024)),
                temperature=float(req.get("temperature", 0.0)),
                top_p=float(req.get("top_p", 1.0)),
                top_k=int(req.get("top_k", 50)),
            )
            _emit({"id": req_id, "text": text})
        except Exception as exc:
            _emit({"id": req_id, "error": str(exc)})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
