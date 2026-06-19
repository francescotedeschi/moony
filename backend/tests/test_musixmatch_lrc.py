from app.musixmatch.client import MusixmatchClient


def test_parse_lrc_ends_line_at_empty_marker():
    body = """\
[00:42.04] And save it for a rainy day
[00:45.76]
[01:06.00] Shadows in the moonlight
"""
    lines = MusixmatchClient.parse_lrc(body)
    assert len(lines) == 2
    assert lines[0].text == "And save it for a rainy day"
    assert lines[0].t_ms == 42_040
    assert lines[0].end_ms == 45_760
    assert lines[1].t_ms == 66_000


def test_parse_lrc_uses_next_lyric_when_no_empty_marker():
    body = """\
[00:22.09] Take this pill, my dear
[00:26.03] It will keep you sharp and clear
"""
    lines = MusixmatchClient.parse_lrc(body)
    assert lines[0].end_ms == 26_030
