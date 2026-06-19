#!/usr/bin/env python3
"""Validate catalog JSON before deploy — V/A range, section coverage, Cyanite fields."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.catalog.validate import ValidationReport, validate_catalog  # noqa: E402


def _default_catalog_path() -> Path:
    return ROOT / "catalog" / "catalog_V17.json"


def _print_report(report: ValidationReport, *, verbose: bool) -> None:
    print(f"Tracks: {report.track_count}  Segments: {report.segment_count}")
    print(f"Errors: {len(report.errors)}  Warnings: {len(report.warnings)}")
    print()

    shown = 0
    limit = 50 if not verbose else len(report.issues)

    for issue in report.issues:
        if shown >= limit:
            remaining = len(report.issues) - shown
            print(f"... and {remaining} more issue(s). Use --verbose to see all.")
            break
        prefix = "ERROR" if issue.level == "error" else "WARN "
        line = f"{prefix} [{issue.code}] {issue.track_id}: {issue.message}"
        print(line)
        if issue.detail:
            print(f"       → {issue.detail}")
        shown += 1

    print()
    if report.ok:
        if report.warnings:
            print("Validation passed with warnings.")
        else:
            print("Validation passed.")
    else:
        print("Validation failed — fix errors before deploy.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MoodPad / MOSS catalog.json")
    parser.add_argument(
        "catalog",
        nargs="?",
        type=Path,
        default=_default_catalog_path(),
        help="Path to catalog.json (default: catalog/catalog.json)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print every issue (default: first 50)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (non-zero exit)",
    )
    args = parser.parse_args()

    path: Path = args.catalog
    if not path.is_file():
        print(f"Catalog not found: {path}", file=sys.stderr)
        return 2

    data = json.loads(path.read_text(encoding="utf-8"))
    report = validate_catalog(data)
    _print_report(report, verbose=args.verbose)

    if not report.ok:
        return 1
    if args.strict and report.warnings:
        print("Strict mode: warnings treated as failure.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
