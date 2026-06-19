"""Cyanite.ai GraphQL client ? upload, analyze, fetch V7 segment mood."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

CYANITE_API_URL = "https://api.cyanite.ai/graphql"

FILE_UPLOAD_REQUEST = """
mutation FileUploadRequest {
  fileUploadRequest {
    id
    uploadUrl
  }
}
"""

LIBRARY_TRACK_CREATE = """
mutation LibraryTrackCreate($input: LibraryTrackCreateInput!) {
  libraryTrackCreate(input: $input) {
    __typename
    ... on LibraryTrackCreateSuccess {
      createdLibraryTrack { id }
    }
    ... on LibraryTrackCreateError {
      code
      message
    }
  }
}
"""

LIBRARY_TRACK_ENQUEUE = """
mutation LibraryTrackEnqueue($input: LibraryTrackEnqueueInput!) {
  libraryTrackEnqueue(input: $input) {
    __typename
    ... on LibraryTrackEnqueueSuccess {
      enqueuedLibraryTrack { id }
    }
    ... on LibraryTrackEnqueueError {
      code
      message
    }
  }
}
"""

LIBRARY_TRACK_STATUS = """
query LibraryTrackStatus($id: ID!) {
  libraryTrack(id: $id) {
    __typename
    ... on LibraryTrackNotFoundError {
      message
    }
    ... on LibraryTrack {
      id
      audioAnalysisV7 {
        __typename
        ... on AudioAnalysisV7Failed {
          error { message }
        }
      }
    }
  }
}
"""


LIBRARY_TRACKS_DELETE = """
mutation LibraryTracksDelete($input: LibraryTracksDeleteInput!) {
  libraryTracksDelete(input: $input) {
    __typename
    ... on LibraryTracksDeleteError {
      code
      message
    }
  }
}
"""

LIBRARY_TRACKS_LIST = """
query LibraryTracksList($first: Int!) {
  libraryTracks(first: $first) {
    edges {
      node {
        id
        externalId
        title
      }
    }
  }
}
"""
LIBRARY_TRACK_ANALYSIS = """
query LibraryTrackAnalysis($id: ID!) {
  libraryTrack(id: $id) {
    __typename
    ... on LibraryTrackNotFoundError {
      message
    }
    ... on LibraryTrack {
      id
      title
      audioAnalysisV7 {
        __typename
        ... on AudioAnalysisV7Finished {
          result {
            genreTags
            freeGenreTags
            segments {
              timestamps
              valence
              arousal
              mood {
                aggressive
                calm
                chilled
                dark
                energetic
                epic
                happy
                romantic
                sad
                scary
                sexy
                ethereal
                uplifting
              }
            }
          }
        }
        ... on AudioAnalysisV7Failed {
          error { message }
        }
      }
    }
  }
}
"""


class CyaniteError(RuntimeError):
    pass


@dataclass(frozen=True)
class CyaniteSegmentSlice:
    start_sec: float
    end_sec: float
    valence: float
    arousal: float
    mood_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class CyaniteTrackAnalysis:
    library_track_id: str
    status: str
    bpm: int = 0
    key: str = ""
    genre_tags: list[str] = field(default_factory=list)
    free_genre_tags: list[str] = field(default_factory=list)
    segments: list[CyaniteSegmentSlice] = field(default_factory=list)
    error_message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class CyaniteClient:
    def __init__(
        self,
        access_token: str,
        *,
        api_url: str = CYANITE_API_URL,
        sleep_sec: float = 0.3,
        poll_interval_sec: float = 5.0,
        poll_timeout_sec: float = 900.0,
        timeout_sec: float = 120.0,
    ) -> None:
        if not access_token.strip():
            raise ValueError("CYANITE_ACCESS_TOKEN is required")
        self._access_token = access_token.strip()
        self._api_url = api_url.rstrip("/")
        self._sleep_sec = sleep_sec
        self._poll_interval_sec = poll_interval_sec
        self._poll_timeout_sec = poll_timeout_sec
        self._client = httpx.Client(
            timeout=timeout_sec,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CyaniteClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        retries: int = 3,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                response = self._client.post(self._api_url, json=payload)
                response.raise_for_status()
                body = response.json()
                if body.get("errors"):
                    raise CyaniteError(json.dumps(body["errors"], ensure_ascii=False))
                return body.get("data") or {}
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt + 1 >= retries:
                    break
                time.sleep(min(2.0 * (attempt + 1), 10.0))
        assert last_exc is not None
        raise last_exc

    def request_file_upload(self) -> tuple[str, str]:
        data = self.graphql(FILE_UPLOAD_REQUEST)
        upload = data.get("fileUploadRequest") or {}
        upload_id = str(upload.get("id") or "")
        upload_url = str(upload.get("uploadUrl") or "")
        if not upload_id or not upload_url:
            raise CyaniteError(f"fileUploadRequest failed: {data}")
        time.sleep(self._sleep_sec)
        return upload_id, upload_url


    def list_library_tracks(self, *, first: int = 50) -> list[dict[str, object]]:
        first = min(max(first, 1), 50)
        data = self.graphql(LIBRARY_TRACKS_LIST, {"first": first})
        edges = (data.get("libraryTracks") or {}).get("edges") or []
        return [edge.get("node") or {} for edge in edges if edge.get("node")]

    def delete_library_tracks(
        self,
        library_track_ids: list[str],
        *,
        batch_size: int = 15,
    ) -> None:
        if not library_track_ids:
            return
        batch_size = max(1, batch_size)
        for offset in range(0, len(library_track_ids), batch_size):
            chunk = library_track_ids[offset : offset + batch_size]
            data = self.graphql(
                LIBRARY_TRACKS_DELETE,
                {"input": {"libraryTrackIds": chunk}},
            )
            result = data.get("libraryTracksDelete") or {}
            typename = str(result.get("__typename") or "")
            if typename.endswith("Error"):
                raise CyaniteError(
                    f"libraryTracksDelete {result.get('code')}: {result.get('message')}"
                )
            time.sleep(self._sleep_sec)

    def probe_library_capacity(self, *, max_probe: int = 50) -> dict[str, object]:
        """Return current library size (API max 50 tracks per list query)."""
        tracks = self.list_library_tracks(first=min(max_probe, 50))
        return {"library_count": len(tracks), "tracks": tracks, "max_probe": min(max_probe, 50)}

    def register_library_track(self, audio_path: Path, external_id: str) -> str:
        """Upload MP3 and create library track without waiting for analysis."""
        upload_id, upload_url = self.request_file_upload()
        self.upload_file(audio_path, upload_url)
        return self.create_library_track(upload_id, external_id)

    def cleanup_library(self, *, keep_external_ids: set[str] | None = None) -> int:
        """Delete all library tracks except those matching keep_external_ids."""
        keep = keep_external_ids or set()
        removed = 0
        while True:
            tracks = self.list_library_tracks()
            delete_ids = [
                str(track["id"])
                for track in tracks
                if str(track.get("externalId") or "") not in keep and track.get("id")
            ]
            if not delete_ids:
                break
            self.delete_library_tracks(delete_ids)
            removed += len(delete_ids)
        return removed

    def probe_library_size_limit(
        self,
        audio_path: Path,
        *,
        max_attempts: int = 100,
        create_interval_sec: float = 7.0,
        cleanup: bool = True,
    ) -> dict[str, object]:
        """Upload probe tracks until librarySizeLimitExceededError; optional cleanup."""
        created: list[str] = []
        limit_code = ""
        limit_message = ""
        rate_waits = 0

        for index in range(max_attempts):
            if limit_code:
                break
            external_id = f"probe_limit_{index}_{int(time.time())}"
            while True:
                try:
                    library_track_id = self.register_library_track(audio_path, external_id)
                    created.append(library_track_id)
                    break
                except CyaniteError as exc:
                    message = str(exc)
                    if "librarySizeLimitExceededError" in message:
                        limit_code = "librarySizeLimitExceededError"
                        limit_message = message
                        break
                    if "rateLimitExceeded" in message:
                        rate_waits += 1
                        time.sleep(max(create_interval_sec, 65.0))
                        continue
                    raise
            if limit_code:
                break
            time.sleep(create_interval_sec)

        result: dict[str, object] = {
            "library_size_limit": len(created) if limit_code else None,
            "library_size_at_least": len(created),
            "limit_reached": bool(limit_code),
            "created_count": len(created),
            "limit_code": limit_code or None,
            "limit_message": limit_message or None,
            "rate_limit_waits": rate_waits,
            "cleaned_up": 0,
        }
        if cleanup and created:
            try:
                self.delete_library_tracks(created)
                result["cleaned_up"] = len(created)
            except Exception as exc:
                result["cleanup_error"] = str(exc)
        return result

    def upload_file(self, audio_path: Path, upload_url: str) -> None:
        body = audio_path.read_bytes()
        # Presigned S3 URL: must not send Cyanite Bearer Authorization header.
        response = httpx.put(
            upload_url,
            content=body,
            headers={"Content-Type": "audio/mpeg"},
            timeout=self._client.timeout,
        )
        if response.status_code != 200:
            raise CyaniteError(
                f"Upload failed ({response.status_code}): {response.text[:300]}"
            )
        time.sleep(self._sleep_sec)

    def create_library_track(self, upload_id: str, external_id: str) -> str:
        data = self.graphql(
            LIBRARY_TRACK_CREATE,
            {"input": {"uploadId": upload_id, "externalId": external_id}},
        )
        result = data.get("libraryTrackCreate") or {}
        typename = str(result.get("__typename") or "")
        if typename == "LibraryTrackCreateError":
            raise CyaniteError(
                f"libraryTrackCreate {result.get('code')}: {result.get('message')}"
            )
        track = result.get("createdLibraryTrack") or {}
        library_track_id = str(track.get("id") or "")
        if not library_track_id:
            raise CyaniteError(f"libraryTrackCreate missing id: {data}")
        time.sleep(self._sleep_sec)
        return library_track_id

    def enqueue_library_track(self, library_track_id: str) -> None:
        data = self.graphql(
            LIBRARY_TRACK_ENQUEUE,
            {"input": {"libraryTrackId": library_track_id}},
        )
        result = data.get("libraryTrackEnqueue") or {}
        typename = str(result.get("__typename") or "")
        if typename.endswith("Error"):
            raise CyaniteError(
                f"libraryTrackEnqueue {result.get('code')}: {result.get('message')}"
            )
        time.sleep(self._sleep_sec)

    def upload_and_analyze(
        self,
        audio_path: Path,
        external_id: str,
        *,
        enqueue_if_needed: bool = True,
    ) -> str:
        upload_id, upload_url = self.request_file_upload()
        self.upload_file(audio_path, upload_url)
        library_track_id = self.create_library_track(upload_id, external_id)
        status = self.get_analysis_status(library_track_id)
        if enqueue_if_needed and status in {"not_started", "not_authorized"}:
            try:
                self.enqueue_library_track(library_track_id)
            except CyaniteError:
                pass
        return library_track_id

    def get_analysis_status(self, library_track_id: str) -> str:
        payload = self._fetch_library_track(library_track_id)
        analysis = payload.get("audioAnalysisV7") or {}
        typename = str(analysis.get("__typename") or "unknown")
        return _normalize_analysis_status(typename)

    def wait_for_analysis(self, library_track_id: str) -> str:
        deadline = time.monotonic() + self._poll_timeout_sec
        last_status = "unknown"
        while time.monotonic() < deadline:
            last_status = self.get_analysis_status(library_track_id)
            if last_status in {"done", "failed", "not_authorized"}:
                return last_status
            time.sleep(self._poll_interval_sec)
        raise CyaniteError(
            f"Timed out waiting for Cyanite analysis ({library_track_id}, last={last_status})"
        )

    def fetch_track_analysis(
        self,
        library_track_id: str,
        *,
        duration_sec: float = 0.0,
    ) -> CyaniteTrackAnalysis:
        payload = self._fetch_library_track_analysis(library_track_id)
        return parse_library_track_analysis(
            library_track_id,
            payload,
            duration_sec=duration_sec,
        )


    def _fetch_library_track_analysis(self, library_track_id: str) -> dict[str, Any]:
        data = self.graphql(LIBRARY_TRACK_ANALYSIS, {"id": library_track_id})
        track = data.get("libraryTrack") or {}
        typename = str(track.get("__typename") or "")
        if typename == "LibraryTrackNotFoundError":
            raise CyaniteError(track.get("message") or "library track not found")
        if typename != "LibraryTrack":
            raise CyaniteError(f"Unexpected libraryTrack type: {typename}")
        return track

    def _fetch_library_track(self, library_track_id: str) -> dict[str, Any]:
        data = self.graphql(LIBRARY_TRACK_STATUS, {"id": library_track_id})
        track = data.get("libraryTrack") or {}
        typename = str(track.get("__typename") or "")
        if typename == "LibraryTrackNotFoundError":
            raise CyaniteError(track.get("message") or "library track not found")
        if typename != "LibraryTrack":
            raise CyaniteError(f"Unexpected libraryTrack type: {typename}")
        return track




def _parse_tag_list(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _parse_free_genre_tags(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    return []



def parse_library_track_analysis(
    library_track_id: str,
    payload: dict[str, Any],
    *,
    duration_sec: float = 0.0,
) -> CyaniteTrackAnalysis:
    """Build analysis from a cached libraryTrack GraphQL payload."""
    analysis = payload.get("audioAnalysisV7") or {}
    typename = str(analysis.get("__typename") or "unknown")
    status = _normalize_analysis_status(typename)
    if status == "failed":
        error = (analysis.get("error") or {}).get("message") or "analysis failed"
        return CyaniteTrackAnalysis(
            library_track_id=library_track_id,
            status="failed",
            error_message=str(error),
            raw=payload,
        )
    if status != "done":
        return CyaniteTrackAnalysis(
            library_track_id=library_track_id,
            status=status,
            raw=payload,
        )

    result = analysis.get("result") or {}
    segments = _parse_segments(result.get("segments") or {}, duration_sec)
    return CyaniteTrackAnalysis(
        library_track_id=library_track_id,
        status="done",
        bpm=int(result.get("bpm") or 0),
        key=str(result.get("key") or ""),
        genre_tags=_parse_tag_list(result.get("genreTags")),
        free_genre_tags=_parse_free_genre_tags(result.get("freeGenreTags")),
        segments=segments,
        raw=payload,
    )

def _normalize_analysis_status(typename: str) -> str:
    mapping = {
        "AudioAnalysisV7NotStarted": "not_started",
        "AudioAnalysisV7Enqueued": "enqueued",
        "AudioAnalysisV7Processing": "processing",
        "AudioAnalysisV7Finished": "done",
        "AudioAnalysisV7Failed": "failed",
        "AudioAnalysisV7NotAuthorized": "not_authorized",
    }
    return mapping.get(typename, typename.lower())


def _parse_segments(raw_segments: dict[str, Any], duration_sec: float) -> list[CyaniteSegmentSlice]:
    timestamps = [float(x) for x in (raw_segments.get("timestamps") or [])]
    valence = [float(x) for x in (raw_segments.get("valence") or [])]
    arousal = [float(x) for x in (raw_segments.get("arousal") or [])]
    mood_raw = raw_segments.get("mood") or {}
    mood_by_tag: dict[str, list[float]] = {}
    if isinstance(mood_raw, dict):
        for tag, values in mood_raw.items():
            if isinstance(values, list):
                mood_by_tag[str(tag)] = [float(v) for v in values]

    if not timestamps:
        return []

    slices: list[CyaniteSegmentSlice] = []
    for i, start in enumerate(timestamps):
        end = timestamps[i + 1] if i + 1 < len(timestamps) else (duration_sec or start + 15.0)
        mood_scores = {
            tag: values[i] for tag, values in mood_by_tag.items() if i < len(values)
        }
        slices.append(
            CyaniteSegmentSlice(
                start_sec=start,
                end_sec=end,
                valence=valence[i] if i < len(valence) else 0.0,
                arousal=arousal[i] if i < len(arousal) else 0.0,
                mood_scores=mood_scores,
            )
        )
    return slices


def load_cache_index(cache_dir: Path) -> dict[str, Any]:
    path = cache_dir / "index.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_cache_index(cache_dir: Path, index: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
