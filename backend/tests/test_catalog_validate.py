from app.catalog.validate import validate_catalog


def test_validate_ok_catalog():
    data = {
        "tracks": [
            {
                "id": "t1",
                "segments": [
                    {"label": "intro", "v": 0.2, "ar": -0.4, "end_sec": 30},
                    {"label": "chorus", "v": 0.5, "ar": 0.6, "end_sec": 60},
                ],
                "transitions": [{"from_seg": 0, "to_seg": 1, "dv": 0.3, "dar": 1.0}],
            }
        ]
    }
    report = validate_catalog(data)
    assert report.ok
    assert not report.errors


def test_validate_segment_out_of_range():
    data = {
        "tracks": [
            {
                "id": "bad",
                "segments": [{"label": "x", "valence": 1.5, "arousal": 0.0, "end_sec": 10}],
            }
        ]
    }
    report = validate_catalog(data)
    assert not report.ok
    assert any(i.code == "va_out_of_range" for i in report.errors)


def test_validate_delta_out_of_range():
    data = {
        "tracks": [
            {
                "id": "bad_delta",
                "segments": [
                    {"label": "a", "v": -1.0, "ar": -1.0, "end_sec": 10},
                    {"label": "b", "v": 1.0, "ar": 1.0, "end_sec": 20},
                ],
            }
        ]
    }
    report = validate_catalog(data)
    assert not report.ok
    assert any(i.code == "delta_out_of_range" for i in report.errors)


def test_validate_zero_va_warning():
    data = {
        "tracks": [
            {
                "id": "placeholder",
                "segments": [{"label": "intro", "valence": 0.0, "arousal": 0.0, "end_sec": 10}],
            }
        ]
    }
    report = validate_catalog(data)
    assert report.ok
    assert any(i.code == "zero_va" for i in report.warnings)


def test_validate_v17_sections_structure_label():
    data = {
        "version": "1.7",
        "tracks": [
            {
                "id": "t1",
                "sections": [
                    {
                        "structure_label": "intro",
                        "valence": 0.2,
                        "arousal": -0.4,
                        "start_sec": 0,
                        "end_sec": 30,
                    },
                    {
                        "structure_label": "chorus",
                        "valence": 0.5,
                        "arousal": 0.6,
                        "start_sec": 30,
                        "end_sec": 60,
                    },
                ],
            }
        ],
    }
    report = validate_catalog(data)
    assert report.ok
    assert report.segment_count == 2


def test_validate_stored_transition_out_of_range():
    data = {
        "tracks": [
            {
                "id": "bad_trans",
                "segments": [
                    {"label": "a", "v": 0.0, "ar": 0.0, "end_sec": 10},
                    {"label": "b", "v": 0.0, "ar": 0.0, "end_sec": 20},
                ],
                "transitions": [{"from_seg": 0, "to_seg": 1, "dv": 0.0, "dar": 1.4}],
            }
        ]
    }
    report = validate_catalog(data)
    assert not report.ok
    assert any(i.code == "transition_out_of_range" for i in report.errors)
