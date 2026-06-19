"""Subprocess entrypoint for MOSS-Music inference (Transformers path)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    import os

    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TQDM_DISABLE", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--top-k", type=int, default=50)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    from analyzer.analyzers.moss_infer_core import infer_moss, load_moss_model

    processor, model = load_moss_model(repo, Path(args.model))
    text = infer_moss(
        processor,
        model,
        audio_path=args.audio,
        prompt=args.prompt,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        top_k=args.top_k,
    )
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
