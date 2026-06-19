from app.catalog.normalize import normalize_catalog
from app.matching.engine import find_best_match
from app.matching.motion_match import (
    dj_playback_rates,
    effective_segment_label,
    refine_entry_ms,
    segment_is_outro_at,
    seek_direction,
    va_at_track_time,
)
from app.models.catalog import VA


def _track_with_motion() -> dict:
    v_curve = [-0.8, -0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.8, 0.75, 0.7]
    a_curve = [-0.5, -0.4, -0.3, -0.1, 0.0, 0.2, 0.3, 0.5, 0.6, 0.7, 0.7, 0.65, 0.6]
    return {
        "id": "motion_a",
        "title": "A",
        "artist": "X",
        "duration_sec": 12.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/a.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 5.0,
                "valence": -0.7,
                "arousal": -0.5,
                "label": "sad",
                "emotion_label": "sad",
            },
            {
                "start_sec": 5.0,
                "end_sec": 9.0,
                "valence": 0.8,
                "arousal": 0.6,
                "label": "happy",
                "emotion_label": "joy",
            },
            {
                "start_sec": 9.0,
                "end_sec": 12.0,
                "valence": 0.75,
                "arousal": 0.55,
                "label": "coda",
                "emotion_label": "joy",
            },
        ],
        "motion": {
            "hop_sec": 1.0,
            "energy": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5],
            "vocal": [0.2] * 13,
            "valence_smooth": v_curve,
            "arousal_smooth": a_curve,
            "mood": [50 + 25 * v + 25 * a for v, a in zip(v_curve, a_curve, strict=True)],
        },
    }


def test_dj_playback_rates():
    start, end = dj_playback_rates(110, 100)
    assert start == 1.1
    assert end == 1.0
    start_clamped, _ = dj_playback_rates(200, 100)
    assert start_clamped == 1.15


def test_seek_direction_uses_current_mood_not_drag():
    target = VA(v=0.8, ar=0.6)
    current = VA(v=-0.7, ar=-0.5)
    seek = seek_direction(target, current, VA(v=0.01, ar=0.0))
    assert seek.v > 0.5
    assert seek.ar > 0.5


def test_target_entry_after_playhead_moves_forward():
    from app.matching.motion_match import best_target_entry_on_track

    cat = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [_track_with_motion()]}
    )
    track = cat.tracks[0]
    joy = VA(v=0.75, ar=0.65)
    from_start, _, _ = best_target_entry_on_track(track, joy, after_t_sec=0.0)
    after_playhead, _, _ = best_target_entry_on_track(track, joy, after_t_sec=0.5)
    assert after_playhead >= from_start


def test_refine_entry_picks_high_valence_region():
    cat = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [_track_with_motion(), _track_with_motion()]}
    )
    cat.tracks[1].id = "motion_b"
    track = cat.tracks[0]
    seg = track.segments[0]
    start_ms, entry_va = refine_entry_ms(track, seg, VA(v=0.7, ar=0.6))
    assert start_ms >= 5000
    assert entry_va.v > 0.3


def test_same_track_jumps_forward_to_joy_region():
    cat = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [_track_with_motion()]}
    )
    current = cat.tracks[0]
    result = find_best_match(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        VA(v=0.0, ar=0.0),
        110,
        set(),
        current_t_ms=500,
        current_track=current,
    )
    assert result is not None
    track, _seg, _idx, _score, start_ms, entry_va, _md, _mq, el = result
    assert el == "happy"
    assert track.id == current.id
    assert start_ms >= 4000
    assert entry_va.v > 0.35


def test_find_best_match_joy_from_sad_playback():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_track_with_motion(), _track_with_motion()],
        }
    )
    cat.tracks[1].id = "other"
    current = cat.tracks[0]
    result = find_best_match(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        VA(v=0.0, ar=0.0),
        110,
        {current.id},
        current_t_ms=500,
        current_track=current,
    )
    assert result is not None
    _track, _seg, _idx, _score, start_ms, entry_va, _md, _mq, el = result
    assert el == "happy"
    assert entry_va.v > 0.35
    assert start_ms >= 4000


def test_forward_search_blends_motion_at_next_section():
    """Near a section boundary, search target shifts toward motion at the next segment."""
    from app.matching.core import _resolve_forward_search_target

    cat = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [_track_with_motion()]}
    )
    track = cat.tracks[0]
    # End of sad segment (4.5s): pad Joy target should pull toward joy motion at 5s
    search, label = _resolve_forward_search_target(
        VA(v=0.8, ar=0.6),
        current_track=track,
        current_t_ms=4500,
    )
    assert label == "happy"
    assert search.v > 0.5


def test_same_track_match_prefers_upcoming_section_motion():
    """On current track, entry is in a later section guided by motion, not the sad head."""
    cat = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [_track_with_motion()]}
    )
    current = cat.tracks[0]
    result = find_best_match(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        VA(v=0.0, ar=0.0),
        110,
        set(),
        current_t_ms=1000,
        current_track=current,
    )
    assert result is not None
    _t, _s, _i, _sc, start_ms, entry_va, _md, _mq, el = result
    assert el == "happy"
    assert start_ms >= 4000
    assert entry_va.v > 0.35


def test_skip_current_track_when_next_two_segments_leave_target_mood():
    """If seg+1 and seg+2 are not the pad target mood, match another track with target mood."""
    current_track = {
        "id": "current_mixed",
        "title": "Current",
        "artist": "X",
        "duration_sec": 12.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/c.mp3", "tags": []},
        "segments": [
            {"start_sec": 0.0, "end_sec": 4.0, "valence": -0.7, "arousal": -0.5, "label": "s0", "emotion_label": "sad"},
            {"start_sec": 4.0, "end_sec": 8.0, "valence": 0.8, "arousal": 0.6, "label": "s1", "emotion_label": "joy"},
            {"start_sec": 8.0, "end_sec": 12.0, "valence": 0.8, "arousal": 0.6, "label": "s2", "emotion_label": "joy"},
        ],
        "motion": {
            "hop_sec": 1.0,
            "energy": [0.5] * 13,
            "vocal": [0.2] * 13,
            "valence_smooth": [-0.7, -0.5, -0.2, 0.2, 0.5, 0.7, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8],
            "arousal_smooth": [-0.5, -0.4, -0.2, 0.1, 0.3, 0.5, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6],
            "mood": [50.0] * 13,
        },
    }
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                current_track,
                {
                    "id": "other_sad",
                    "title": "Other Sad",
                    "artist": "Y",
                    "duration_sec": 100.0,
                    "primary_emotion": "calm",
                    "jamendo": {"audio_url": "https://example.com/s.mp3", "tags": []},
                    "segments": [
                        {
                            "start_sec": 0.0,
                            "end_sec": 8.0,
                            "valence": 0.8,
                            "arousal": 0.6,
                            "label": "intro",
                            "emotion_label": "joy",
                        },
                        {
                            "start_sec": 8.0,
                            "end_sec": 50.0,
                            "valence": -0.7,
                            "arousal": -0.5,
                            "label": "main",
                            "emotion_label": "sad",
                        },
                        {
                            "start_sec": 50.0,
                            "end_sec": 100.0,
                            "valence": -0.7,
                            "arousal": -0.5,
                            "label": "coda",
                            "emotion_label": "sad",
                        },
                    ],
                    "motion": {
                        "hop_sec": 1.0,
                        "energy": [0.4] * 11,
                        "vocal": [0.2] * 11,
                        "valence_smooth": [-0.7] * 11,
                        "arousal_smooth": [-0.5] * 11,
                        "mood": [50.0] * 11,
                    },
                },
            ],
        }
    )
    current = cat.tracks[0]
    # Playhead in sad (1s); target Joy; next two segments are joy → stay on current track
    stay = find_best_match(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        VA(v=0.0, ar=0.0),
        110,
        set(),
        current_t_ms=1000,
        current_track=current,
    )
    assert stay is not None
    assert stay[0].id == current.id

    # Target Sad: next two segments are joy → skip to other_sad
    result = find_best_match(
        cat.tracks,
        VA(v=-0.7, ar=-0.5),
        VA(v=0.0, ar=0.0),
        110,
        set(),
        current_t_ms=1000,
        current_track=current,
    )
    assert result is not None
    track, _seg, _idx, _score, _ms, _va, _md, _mq, el = result
    assert track.id == "other_sad"
    assert el == "sad"


def test_match_never_enters_outro_segment():
    track = {
        "id": "with_outro",
        "title": "T",
        "artist": "X",
        "duration_sec": 20.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/t.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 4.0,
                "valence": 0.0,
                "arousal": 0.0,
                "label": "intro",
                "emotion_label": "calm",
            },
            {
                "start_sec": 4.0,
                "end_sec": 12.0,
                "valence": 0.8,
                "arousal": 0.6,
                "label": "chorus",
                "emotion_label": "joy",
            },
            {
                "start_sec": 12.0,
                "end_sec": 20.0,
                "valence": 0.7,
                "arousal": 0.5,
                "label": "outro",
                "emotion_label": "joy",
            },
        ],
        "motion": {
            "hop_sec": 1.0,
            "energy": [0.6] * 21,
            "vocal": [0.2] * 21,
            "valence_smooth": [0.2] * 4 + [0.8] * 8 + [0.7] * 9,
            "arousal_smooth": [0.1] * 4 + [0.6] * 8 + [0.5] * 9,
            "mood": [50.0] * 21,
        },
    }
    cat = normalize_catalog(
        {"catalog_schema": "moodpad-catalog-musicathon", "tracks": [track]}
    )
    result = find_best_match(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        VA(v=0.0, ar=0.0),
        110,
        set(),
    )
    assert result is not None
    _t, seg, _i, _sc, start_ms, _va, _md, _mq, _el = result
    assert seg.label != "outro"
    assert start_ms < 12_000


def test_skip_current_track_when_playhead_in_outro():
    current_track = {
        "id": "in_outro",
        "title": "Current",
        "artist": "X",
        "duration_sec": 20.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/c.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 12.0,
                "valence": 0.8,
                "arousal": 0.6,
                "label": "chorus",
                "emotion_label": "joy",
            },
            {
                "start_sec": 12.0,
                "end_sec": 20.0,
                "valence": 0.7,
                "arousal": 0.5,
                "label": "outro",
                "emotion_label": "joy",
            },
        ],
        "motion": {
            "hop_sec": 1.0,
            "energy": [0.6] * 21,
            "vocal": [0.2] * 21,
            "valence_smooth": [0.75] * 12 + [0.7] * 9,
            "arousal_smooth": [0.6] * 21,
            "mood": [50.0] * 21,
        },
    }
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                current_track,
                {
                    "id": "other_joy",
                    "title": "Other",
                    "artist": "Y",
                    "duration_sec": 100.0,
                    "primary_emotion": "calm",
                    "jamendo": {"audio_url": "https://example.com/j.mp3", "tags": []},
                    "segments": [
                        {
                            "start_sec": 0.0,
                            "end_sec": 8.0,
                            "valence": 0.0,
                            "arousal": 0.0,
                            "label": "intro",
                            "emotion_label": "calm",
                        },
                        {
                            "start_sec": 8.0,
                            "end_sec": 50.0,
                            "valence": 0.8,
                            "arousal": 0.6,
                            "label": "verse",
                            "emotion_label": "joy",
                        },
                        {
                            "start_sec": 50.0,
                            "end_sec": 100.0,
                            "valence": 0.75,
                            "arousal": 0.55,
                            "label": "coda",
                            "emotion_label": "joy",
                        },
                    ],
                    "motion": {
                        "hop_sec": 1.0,
                        "energy": [0.5] * 101,
                        "vocal": [0.2] * 101,
                        "valence_smooth": [0.2] * 8 + [0.8] * 42 + [0.75] * 51,
                        "arousal_smooth": [0.1] * 8 + [0.6] * 42 + [0.55] * 51,
                        "mood": [50.0] * 101,
                    },
                },
            ],
        }
    )
    result = find_best_match(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        VA(v=0.0, ar=0.0),
        110,
        set(),
        current_t_ms=14_000,
        current_track=cat.tracks[0],
    )
    assert result is not None
    assert result[0].id == "other_joy"


def test_skip_current_track_when_next_segment_is_outro():
    """Outro ahead → another track with the same pad target mood, not a later segment here."""
    current_track = {
        "id": "current_outro",
        "title": "Current",
        "artist": "X",
        "duration_sec": 20.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/c.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 12.0,
                "valence": 0.8,
                "arousal": 0.6,
                "label": "chorus",
                "emotion_label": "joy",
            },
            {
                "start_sec": 12.0,
                "end_sec": 20.0,
                "valence": 0.75,
                "arousal": 0.55,
                "label": "outro",
                "emotion_label": "joy",
            },
        ],
        "motion": {
            "hop_sec": 1.0,
            "energy": [0.6] * 21,
            "vocal": [0.2] * 21,
            "valence_smooth": [0.75] * 12 + [0.7] * 9,
            "arousal_smooth": [0.6] * 21,
            "mood": [50.0] * 21,
        },
    }
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                current_track,
                {
                    "id": "other_joy",
                    "title": "Other Joy",
                    "artist": "Y",
                    "duration_sec": 100.0,
                    "primary_emotion": "calm",
                    "jamendo": {"audio_url": "https://example.com/j.mp3", "tags": []},
                    "segments": [
                        {
                            "start_sec": 0.0,
                            "end_sec": 8.0,
                            "valence": 0.0,
                            "arousal": 0.0,
                            "label": "intro",
                            "emotion_label": "calm",
                        },
                        {
                            "start_sec": 8.0,
                            "end_sec": 50.0,
                            "valence": 0.8,
                            "arousal": 0.6,
                            "label": "verse",
                            "emotion_label": "joy",
                        },
                        {
                            "start_sec": 50.0,
                            "end_sec": 100.0,
                            "valence": 0.75,
                            "arousal": 0.55,
                            "label": "coda",
                            "emotion_label": "joy",
                        },
                    ],
                    "motion": {
                        "hop_sec": 1.0,
                        "energy": [0.5] * 101,
                        "vocal": [0.2] * 101,
                        "valence_smooth": [0.2] * 8 + [0.8] * 42 + [0.75] * 51,
                        "arousal_smooth": [0.1] * 8 + [0.6] * 42 + [0.55] * 51,
                        "mood": [50.0] * 101,
                    },
                },
            ],
        }
    )
    current = cat.tracks[0]
    result = find_best_match(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        VA(v=0.0, ar=0.0),
        110,
        set(),
        current_t_ms=6000,
        current_track=current,
    )
    assert result is not None
    track, _seg, _idx, _score, start_ms, _va, _md, _mq, el = result
    assert track.id == "other_joy"
    assert el == "happy"
    assert start_ms >= 8000
    assert start_ms < 50_000


def test_find_best_match_uses_motion_entry():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [_track_with_motion(), _track_with_motion()],
        }
    )
    cat.tracks[1].id = "other"
    current = cat.tracks[0]
    result = find_best_match(
        cat.tracks,
        VA(v=0.75, ar=0.65),
        VA(v=0.2, ar=0.1),
        110,
        {current.id},
        current_t_ms=1000,
        current_track=current,
    )
    assert result is not None
    track, seg, _idx, _score, start_ms, entry_va, _md, _mq, el = result
    assert el == "happy"
    assert entry_va.v > 0.35
    assert track.id == "other"
    assert start_ms >= 0
    live = va_at_track_time(current, 1.0)
    assert abs(live.v - (-0.6)) < 0.3


def test_last_segment_forced_as_outro_when_unlabeled():
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                {
                    "id": "forced_outro",
                    "title": "T",
                    "artist": "X",
                    "duration_sec": 20.0,
                    "primary_emotion": "calm",
                    "jamendo": {"audio_url": "https://example.com/t.mp3", "tags": []},
                    "segments": [
                        {
                            "start_sec": 0.0,
                            "end_sec": 14.0,
                            "valence": 0.8,
                            "arousal": 0.6,
                            "label": "chorus",
                            "emotion_label": "joy",
                        },
                        {
                            "start_sec": 14.0,
                            "end_sec": 20.0,
                            "valence": 0.7,
                            "arousal": 0.5,
                            "label": "bridge",
                            "emotion_label": "joy",
                        },
                    ],
                    "motion": {
                        "hop_sec": 1.0,
                        "energy": [0.6] * 21,
                        "vocal": [0.2] * 21,
                        "valence_smooth": [0.8] * 14 + [0.7] * 7,
                        "arousal_smooth": [0.6] * 21,
                        "mood": [50.0] * 21,
                    },
                },
            ],
        }
    )
    track = cat.tracks[0]
    assert segment_is_outro_at(track, 1)
    assert effective_segment_label(track, 1) == "outro"
    assert not segment_is_outro_at(track, 0)


def test_skip_when_next_segment_is_unlabeled_last():
    current_track = {
        "id": "curr",
        "title": "Current",
        "artist": "X",
        "duration_sec": 20.0,
        "primary_emotion": "calm",
        "jamendo": {"audio_url": "https://example.com/c.mp3", "tags": []},
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 12.0,
                "valence": 0.8,
                "arousal": 0.6,
                "label": "chorus",
                "emotion_label": "joy",
            },
            {
                "start_sec": 12.0,
                "end_sec": 20.0,
                "valence": 0.75,
                "arousal": 0.55,
                "label": "coda",
                "emotion_label": "joy",
            },
        ],
        "motion": {
            "hop_sec": 1.0,
            "energy": [0.6] * 21,
            "vocal": [0.2] * 21,
            "valence_smooth": [0.75] * 12 + [0.7] * 9,
            "arousal_smooth": [0.6] * 21,
            "mood": [50.0] * 21,
        },
    }
    cat = normalize_catalog(
        {
            "catalog_schema": "moodpad-catalog-musicathon",
            "tracks": [
                current_track,
                {
                    "id": "other_joy",
                    "title": "Other",
                    "artist": "Y",
                    "duration_sec": 100.0,
                    "primary_emotion": "calm",
                    "jamendo": {"audio_url": "https://example.com/j.mp3", "tags": []},
                    "segments": [
                        {
                            "start_sec": 0.0,
                            "end_sec": 8.0,
                            "valence": 0.0,
                            "arousal": 0.0,
                            "label": "intro",
                            "emotion_label": "calm",
                        },
                        {
                            "start_sec": 8.0,
                            "end_sec": 50.0,
                            "valence": 0.8,
                            "arousal": 0.6,
                            "label": "verse",
                            "emotion_label": "joy",
                        },
                        {
                            "start_sec": 50.0,
                            "end_sec": 100.0,
                            "valence": 0.75,
                            "arousal": 0.55,
                            "label": "coda",
                            "emotion_label": "joy",
                        },
                    ],
                    "motion": {
                        "hop_sec": 1.0,
                        "energy": [0.5] * 101,
                        "vocal": [0.2] * 101,
                        "valence_smooth": [0.2] * 8 + [0.8] * 42 + [0.75] * 51,
                        "arousal_smooth": [0.1] * 8 + [0.6] * 42 + [0.55] * 51,
                        "mood": [50.0] * 101,
                    },
                },
            ],
        }
    )
    result = find_best_match(
        cat.tracks,
        VA(v=0.8, ar=0.6),
        VA(v=0.0, ar=0.0),
        110,
        set(),
        current_t_ms=11_000,
        current_track=cat.tracks[0],
    )
    assert result is not None
    assert result[0].id == "other_joy"
