#!/usr/bin/env python3
"""Unified per-song analysis for catalog V17 (player-facing schema).

Pipeline per track (Musixmatch lyrics are runtime-only — never persisted):

  1. Structure — hybrid (lyrics-LLM + MOSS cuts) by default
  2. MOSS — per-section descriptions
  3. Embeddings — MiniLM from descriptions
  4. Cyanite — section mood/V-A + track energy curve (optional)

Output matches slim ``catalog_V17.json``: structure, description, embedding,
cyanite_mood_* / V-A, and track ``cyanite.energy_curve``. No motion or legacy MOSS mood.

Uses the in-repo ``analyzer`` package (``moony/analyzer``).

Examples:
  # Single track from catalog entry + local MP3
  python3 pipeline/song_analysis.py --catalog catalog/catalog_V17.json --track-id jamendo_1036435

  # Single MP3 (metadata via flags)
  python3 pipeline/song_analysis.py --audio data/all_audio/1036435.mp3 \\
    --track-id jamendo_1036435 --title FLIGHT --artist "Sweet Play"

  # Batch: MOSS only (no Cyanite API)
  python3 pipeline/song_analysis.py --catalog catalog/catalog_V17.json --limit 5 --skip-cyanite

  # Cyanite only for tracks that already have sections
  python3 pipeline/song_analysis.py --catalog catalog/catalog_V17.json --cyanite-only
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

from analyzer.analyzers import get_lyrics_analyzer  # noqa: E402
from analyzer.config import Settings  # noqa: E402
from analyzer.cyanite import (  # noqa: E402
    CyaniteClient,
    CyaniteError,
    load_cache_index,
    parse_library_track_analysis,
    save_cache_index,
)
from analyzer.cyanite_enrich import enrich_track_with_cyanite  # noqa: E402
from analyzer.models import (  # noqa: E402
    CatalogV17Track,
    CyaniteStub,
    JamendoInfo,
    MusixmatchStub,
)
from analyzer.musixmatch import MusixmatchClient  # noqa: E402
from analyzer.section_build import build_sections  # noqa: E402
from analyzer.section_from_lyrics import section_from_lyrics  # noqa: E402
from analyzer.section_hybrid import (  # noqa: E402
    is_moss_fallback_windows,
    merge_lyrics_labels_with_moss_granularity,
)
from slim_catalog_v17 import assert_no_lyrics_in_payload, slim_player_track  # noqa: E402


@dataclass(frozen=True)
class SongInput:
    audio_path: Path
    track_id: str
    title: str
    artist: str
    duration_sec: float = 0.0
    bpm: int = 0
    jamendo: dict[str, Any] | None = None
    musixmatch: dict[str, Any] | None = None


def _resolve_duration(audio_path: Path, duration_sec: float) -> float:
    if duration_sec > 0:
        return duration_sec
    import librosa

    return float(librosa.get_duration(path=str(audio_path)))


def _has_lyrics_flag(mx_raw: dict[str, Any]) -> bool:
    return bool(mx_raw.get("has_lyrics") or mx_raw.get("has_subtitles"))


def _track_needs_moss(raw: dict[str, Any]) -> bool:
    sections = raw.get("sections") or raw.get("segments") or []
    return len(sections) < 2


def _track_needs_cyanite(raw: dict[str, Any]) -> bool:
    cyanite = raw.get("cyanite") or {}
    if str(cyanite.get("status") or "") == "done" and cyanite.get("energy_curve"):
        return False
    sections = raw.get("sections") or []
    return len(sections) >= 2


def song_input_from_catalog_track(raw: dict[str, Any], audio_dir: Path) -> SongInput:
    track_id = str(raw.get("id") or "")
    jamendo_raw = dict(raw.get("jamendo") or {})
    jamendo_id = str(jamendo_raw.get("track_id") or track_id.replace("jamendo_", ""))
    audio_path = audio_dir / f"{jamendo_id}.mp3"
    return SongInput(
        audio_path=audio_path,
        track_id=track_id,
        title=str(raw.get("title") or "?"),
        artist=str(raw.get("artist") or "?"),
        duration_sec=float(raw.get("duration_sec") or 0.0),
        bpm=int(raw.get("bpm") or 0),
        jamendo=jamendo_raw,
        musixmatch=dict(raw.get("musixmatch") or {}),
    )


def song_input_from_audio(
    audio_path: Path,
    *,
    track_id: str,
    title: str,
    artist: str,
    duration_sec: float = 0.0,
    bpm: int = 0,
    jamendo: dict[str, Any] | None = None,
    musixmatch: dict[str, Any] | None = None,
) -> SongInput:
    return SongInput(
        audio_path=audio_path.resolve(),
        track_id=track_id,
        title=title,
        artist=artist,
        duration_sec=duration_sec,
        bpm=bpm,
        jamendo=jamendo,
        musixmatch=musixmatch,
    )


def _build_structure_drafts(
    *,
    analyzer: Any,
    audio_path: Path,
    duration_sec: float,
    lyrics: Any,
    structure_source: str,
) -> list[Any] | None:
    use_lyrics_llm = structure_source == "lyrics-llm"
    use_hybrid = structure_source == "hybrid"

    if not ((use_hybrid or use_lyrics_llm) and lyrics):
        return None

    lyrics_sections = section_from_lyrics(
        lyrics,
        duration_sec,
        title="",
        artist="",
    )
    if use_hybrid:
        moss_sections = analyzer.analyze_structure_only(audio_path, duration_sec)
        moss_fallback = is_moss_fallback_windows(moss_sections, duration_sec, analyzer)
        return merge_lyrics_labels_with_moss_granularity(
            lyrics_sections,
            moss_sections,
            duration_sec,
            moss_is_fallback=moss_fallback,
        )
    return lyrics_sections


def _catalog_track_from_raw(
    raw: dict[str, Any],
    *,
    sections: list[Any] | None = None,
    cyanite: Any | None = None,
) -> Any:
    jamendo = JamendoInfo.model_validate(raw.get("jamendo") or {})
    musixmatch = MusixmatchStub.model_validate(raw.get("musixmatch") or {})
    cyanite_stub = cyanite or CyaniteStub.model_validate(raw.get("cyanite") or {})
    return CatalogV17Track(
        id=str(raw.get("id") or f"jamendo_{jamendo.track_id}"),
        title=str(raw.get("title") or "?"),
        artist=str(raw.get("artist") or "?"),
        duration_sec=float(raw.get("duration_sec") or 0.0),
        bpm=int(raw.get("bpm") or 0),
        jamendo=jamendo,
        sections=list(sections or raw.get("sections") or []),
        musixmatch=musixmatch,
        cyanite=cyanite_stub,
    )


def analyze_moss_sections(
    song: SongInput,
    settings: Any,
    *,
    structure_source: str | None = None,
    analyzer: Any | None = None,
    mx_client: Any | None = None,
) -> Any:
    """MOSS structure + descriptions + embeddings (no Cyanite)."""
    structure_source = (structure_source or settings.v17_structure_source).strip().lower()
    if structure_source not in ("moss", "lyrics-llm", "hybrid"):
        raise ValueError(f"Invalid structure_source: {structure_source!r}")

    own_analyzer = analyzer is None
    own_mx = mx_client is None
    analyzer = analyzer or get_lyrics_analyzer(settings)
    mx = mx_client or MusixmatchClient(
        settings.musixmatch_api_key,
        sleep_sec=settings.musixmatch_sleep_sec,
    )

    if not song.audio_path.is_file():
        raise FileNotFoundError(f"Audio not found: {song.audio_path}")

    duration_sec = _resolve_duration(song.audio_path, song.duration_sec)
    mx_raw = song.musixmatch or {}
    mx_track_id = mx_raw.get("track_id")
    lyrics = None
    needs_synced = structure_source in ("lyrics-llm", "hybrid")
    if mx_track_id and (needs_synced or _has_lyrics_flag(mx_raw)):
        lyrics = mx.fetch_synced_subtitle(mx_track_id)

    structure_drafts = _build_structure_drafts(
        analyzer=analyzer,
        audio_path=song.audio_path,
        duration_sec=duration_sec,
        lyrics=lyrics,
        structure_source=structure_source,
    )
    drafts = analyzer.analyze_with_lyrics(
        song.audio_path,
        duration_sec,
        lyrics,
        structure_drafts=structure_drafts,
    )
    sections = build_sections(drafts, embedding_model=settings.embedding_model)

    raw = {
        "id": song.track_id,
        "title": song.title,
        "artist": song.artist,
        "duration_sec": duration_sec,
        "bpm": song.bpm,
        "jamendo": song.jamendo or {"track_id": 0, "audio_url": ""},
        "musixmatch": mx_raw,
    }
    track = _catalog_track_from_raw(raw, sections=sections)

    if own_mx:
        mx.close()
    if own_analyzer and hasattr(analyzer, "close"):
        analyzer.close()
    return track


def enrich_track_cyanite(
    track: Any,
    settings: Any,
    audio_path: Path,
    *,
    force: bool = False,
) -> Any:
    """Upload/analyze with Cyanite and map mood + energy onto sections."""
    import json as json_mod

    if not force and track.cyanite.status == "done" and track.cyanite.energy_curve:
        return track

    settings.validate_for_cyanite()
    cache_dir = settings.cyanite_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_index = load_cache_index(cache_dir)

    cache_file = cache_dir / f"{track.id}.json"
    if not force and cache_file.is_file():
        payload = json_mod.loads(cache_file.read_text(encoding="utf-8"))
        library_track_id = str(track.cyanite.library_track_id or payload.get("id") or "")
        if library_track_id:
            analysis = parse_library_track_analysis(
                library_track_id,
                payload,
                duration_sec=track.duration_sec,
            )
            if analysis.status == "done":
                return enrich_track_with_cyanite(track, analysis)

    client = CyaniteClient(
        settings.cyanite_access_token,
        api_url=settings.cyanite_api_url,
        sleep_sec=settings.cyanite_sleep_sec,
        poll_interval_sec=settings.cyanite_poll_interval_sec,
        poll_timeout_sec=settings.cyanite_poll_timeout_sec,
    )
    release_slot = settings.cyanite_release_library_slot
    library_track_id = str(track.cyanite.library_track_id or cache_index.get(track.id, {}).get("library_track_id") or "")

    try:
        if not library_track_id:
            library_track_id = client.upload_and_analyze(audio_path, track.id)
            cache_index[track.id] = {"library_track_id": library_track_id, "status": "uploaded"}
            save_cache_index(cache_dir, cache_index)

        status = client.get_analysis_status(library_track_id)
        if status not in {"done", "failed", "not_authorized"}:
            status = client.wait_for_analysis(library_track_id)

        analysis = client.fetch_track_analysis(library_track_id, duration_sec=track.duration_sec)
        if analysis.raw:
            cache_file.write_text(
                json_mod.dumps(analysis.raw, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        if analysis.status == "not_authorized":
            enriched = track.model_copy(
                update={
                    "cyanite": CyaniteStub(
                        library_track_id=library_track_id,
                        status="not_authorized",
                        error_message="Audio Analysis V7 not authorized on this Cyanite account",
                    )
                }
            )
        elif analysis.status == "failed":
            enriched = track.model_copy(
                update={
                    "cyanite": CyaniteStub(
                        library_track_id=library_track_id,
                        status="failed",
                        error_message=analysis.error_message,
                    )
                }
            )
        else:
            enriched = enrich_track_with_cyanite(track, analysis)
            if release_slot:
                try:
                    client.delete_library_tracks([library_track_id])
                except CyaniteError:
                    pass

        cache_index[track.id] = {
            "library_track_id": library_track_id,
            "status": enriched.cyanite.status,
            "source": "api",
        }
        save_cache_index(cache_dir, cache_index)
        return enriched
    finally:
        client.close()


def analyze_song(
    song: SongInput,
    settings: Any,
    *,
    structure_source: str | None = None,
    skip_cyanite: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Run MOSS (+ optional Cyanite) for one track; return a slim player-facing dict."""
    track = analyze_moss_sections(song, settings, structure_source=structure_source)
    if not skip_cyanite:
        track = enrich_track_cyanite(track, settings, song.audio_path, force=force)
    payload = slim_player_track(track.model_dump(mode="json"))
    assert_no_lyrics_in_payload(payload)
    return payload


def analyze_catalog_track(
    raw: dict[str, Any],
    settings: Any,
    audio_dir: Path,
    *,
    structure_source: str | None = None,
    skip_cyanite: bool = False,
    cyanite_only: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    song = song_input_from_catalog_track(raw, audio_dir)
    if not song.audio_path.is_file():
        raise FileNotFoundError(f"Audio not found: {song.audio_path}")

    if cyanite_only:
        track = _catalog_track_from_raw(raw)
        if not track.sections:
            raise ValueError(f"{song.track_id}: no sections for cyanite-only run")
        if not skip_cyanite:
            track = enrich_track_cyanite(track, settings, song.audio_path, force=force)
        payload = slim_player_track(track.model_dump(mode="json"))
        assert_no_lyrics_in_payload(payload)
        return payload

    run_moss = force or _track_needs_moss(raw)
    if run_moss:
        track = analyze_moss_sections(song, settings, structure_source=structure_source)
    else:
        track = _catalog_track_from_raw(raw)

    if not skip_cyanite and (force or _track_needs_cyanite(raw) or run_moss):
        track = enrich_track_cyanite(track, settings, song.audio_path, force=force)

    payload = slim_player_track(track.model_dump(mode="json"))
    # Preserve musixmatch audit fields from source catalog (lyrics_trusted, etc.)
    source_mm = raw.get("musixmatch")
    if isinstance(source_mm, dict):
        merged_mm = dict(payload.get("musixmatch") or {})
        for key in ("lyrics_trusted", "has_synced_subtitles", "subtitle_audit_reasons"):
            if key in source_mm:
                merged_mm[key] = source_mm[key]
        payload["musixmatch"] = merged_mm

    assert_no_lyrics_in_payload(payload)
    return payload


def _merge_track_into_catalog(catalog: dict[str, Any], track_payload: dict[str, Any]) -> None:
    track_id = track_payload["id"]
    tracks = catalog.get("tracks") or []
    for index, existing in enumerate(tracks):
        if isinstance(existing, dict) and existing.get("id") == track_id:
            tracks[index] = track_payload
            return
    tracks.append(track_payload)
    catalog["tracks"] = tracks


def run_batch(
    catalog_path: Path,
    output_path: Path,
    settings: Any,
    audio_dir: Path,
    *,
    track_id: str | None = None,
    limit: int | None = None,
    structure_source: str | None = None,
    skip_cyanite: bool = False,
    cyanite_only: bool = False,
    force: bool = False,
    resume: bool = True,
) -> dict[str, int]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    partial_path = output_path.with_suffix(".partial.json")
    if resume and partial_path.is_file():
        catalog = json.loads(partial_path.read_text(encoding="utf-8"))

    targets: list[dict[str, Any]] = []
    for raw in catalog.get("tracks") or []:
        if not isinstance(raw, dict):
            continue
        if track_id and raw.get("id") != track_id:
            continue
        if cyanite_only:
            if _track_needs_cyanite(raw) or force:
                targets.append(raw)
        elif force or _track_needs_moss(raw) or (not skip_cyanite and _track_needs_cyanite(raw)):
            targets.append(raw)

    if limit is not None:
        targets = targets[:limit]

    stats = {"total": len(catalog.get("tracks") or []), "selected": len(targets), "ok": 0, "failed": 0}

    for i, raw in enumerate(targets, 1):
        tid = raw.get("id", "?")
        print(f"[{i}/{len(targets)}] {tid} — {raw.get('artist')} - {raw.get('title')}")
        try:
            payload = analyze_catalog_track(
                raw,
                settings,
                audio_dir,
                structure_source=structure_source,
                skip_cyanite=skip_cyanite,
                cyanite_only=cyanite_only,
                force=force,
            )
            _merge_track_into_catalog(catalog, payload)
            stats["ok"] += 1
        except Exception as exc:
            stats["failed"] += 1
            print(f"  FAIL {tid}: {exc}", file=sys.stderr)

        catalog["generated_at"] = datetime.now(UTC).isoformat()
        if not skip_cyanite and not cyanite_only:
            catalog["cyanite_status"] = "partial"
        partial_path.write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    assert_no_lyrics_in_payload(catalog)
    output_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if partial_path.exists():
        partial_path.unlink()
    print(f"Wrote {output_path} ({stats['ok']} ok, {stats['failed']} failed)")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze songs into player-facing catalog V17 JSON.")
    parser.add_argument("--audio", type=Path, help="Local MP3 path")
    parser.add_argument("--catalog", type=Path, help="Catalog JSON (batch or single track lookup)")
    parser.add_argument("--track-id", help="Track id e.g. jamendo_1036435")
    parser.add_argument("--title", help="Title when using --audio without --catalog")
    parser.add_argument("--artist", help="Artist when using --audio without --catalog")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output JSON path (single track dict, or catalog for batch)",
    )
    parser.add_argument("--audio-dir", type=Path, help="Folder with {jamendo_id}.mp3")
    parser.add_argument("--limit", "-n", type=int, help="Max tracks in batch mode")
    parser.add_argument(
        "--structure-source",
        choices=("moss", "lyrics-llm", "hybrid"),
        help="Section structure source (default: V17_STRUCTURE_SOURCE env)",
    )
    parser.add_argument("--skip-cyanite", action="store_true", help="MOSS + embeddings only")
    parser.add_argument(
        "--cyanite-only",
        action="store_true",
        help="Skip MOSS; enrich existing sections with Cyanite",
    )
    parser.add_argument("--force", action="store_true", help="Re-run even when data exists")
    parser.add_argument("--no-resume", action="store_true", help="Ignore partial catalog on batch")
    args = parser.parse_args()

    if not args.audio and not args.catalog:
        parser.error("Provide --audio or --catalog")
    if args.audio and not args.catalog and not args.track_id:
        parser.error("--track-id is required with --audio")
    if args.catalog and args.audio:
        parser.error("Use --audio or --catalog, not both")

    settings = Settings.from_env()
    if not args.cyanite_only:
        settings.validate_for_v17_build()
    audio_dir = args.audio_dir or settings.all_audio_dir

    if args.catalog:
        catalog_path = args.catalog if args.catalog.is_absolute() else ROOT / args.catalog
        if not catalog_path.is_file():
            print(f"Catalog not found: {catalog_path}", file=sys.stderr)
            return 2

        if args.track_id and not args.limit:
            raw = next(
                (t for t in json.loads(catalog_path.read_text())["tracks"] if t.get("id") == args.track_id),
                None,
            )
            if raw is None:
                print(f"Track not found: {args.track_id}", file=sys.stderr)
                return 2
            payload = analyze_catalog_track(
                raw,
                settings,
                audio_dir,
                structure_source=args.structure_source,
                skip_cyanite=args.skip_cyanite,
                cyanite_only=args.cyanite_only,
                force=args.force,
            )
            out = args.output or Path(f"{args.track_id}.json")
            out = out if out.is_absolute() else ROOT / out
            out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Wrote {out} ({len(payload.get('sections') or [])} sections)")
            return 0

        output_path = args.output or catalog_path
        output_path = output_path if output_path.is_absolute() else ROOT / output_path
        stats = run_batch(
            catalog_path,
            output_path,
            settings,
            audio_dir,
            track_id=args.track_id,
            limit=args.limit,
            structure_source=args.structure_source,
            skip_cyanite=args.skip_cyanite,
            cyanite_only=args.cyanite_only,
            force=args.force,
            resume=not args.no_resume,
        )
        return 1 if stats["failed"] else 0

    audio_path = args.audio if args.audio.is_absolute() else ROOT / args.audio
    track_id = args.track_id or f"jamendo_{audio_path.stem}"
    song = song_input_from_audio(
        audio_path,
        track_id=track_id,
        title=args.title or track_id,
        artist=args.artist or "",
    )
    track = analyze_moss_sections(song, settings, structure_source=args.structure_source)
    if not args.skip_cyanite:
        track = enrich_track_cyanite(track, settings, audio_path, force=args.force)
    payload = slim_player_track(track.model_dump(mode="json"))
    assert_no_lyrics_in_payload(payload)
    out = args.output or Path(f"{track_id}.json")
    out = out if out.is_absolute() else ROOT / out
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(payload.get('sections') or [])} sections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
