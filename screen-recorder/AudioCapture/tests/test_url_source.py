"""URL mode validation and auth-URL safety tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audiocapture.url_source import validate_web_url, url_recording_stem, autoplay_url


def test_normal_and_query_auth_urls_are_allowed():
    assert validate_web_url("https://example.com/live")[0]
    assert validate_web_url("https://example.com/live?token=abc&expires=123")[0]
    assert validate_web_url("https://id.example.com/login?client_id=demo")[0]


def test_autoplay_is_added_only_for_supported_video_sites():
    url, provider = autoplay_url("https://www.youtube.com/watch?v=abc&list=xyz")
    assert provider == "YouTube" and "autoplay=1" in url
    assert "v=abc" in url and "list=xyz" in url
    unchanged, provider = autoplay_url("https://example.test/player?id=5")
    assert provider is None and unchanged == "https://example.test/player?id=5"
    vimeo, provider = autoplay_url("https://player.vimeo.com/video/123")
    assert provider == "Vimeo player" and "autoplay=1" in vimeo


def test_playlist_stem_is_indexed_and_does_not_expose_url():
    stem = url_recording_stem(1, "example.com - track/name", "Recording 2026-11-08")
    assert stem == "02 - example.com - trackname - Recording 2026-11-08"
    assert "token" not in stem


def test_incomplete_or_unsafe_urls_are_rejected():
    for value in ("", "example.com/audio", "file:///tmp/a.wav", "ftp://example.com/a"):
        assert not validate_web_url(value)[0], value
    assert not validate_web_url("https://alice:secret@example.com/audio")[0]
    assert not validate_web_url("https://example.com:bad/audio")[0]


if __name__ == "__main__":
    test_normal_and_query_auth_urls_are_allowed()
    test_autoplay_is_added_only_for_supported_video_sites()
    test_playlist_stem_is_indexed_and_does_not_expose_url()
    test_incomplete_or_unsafe_urls_are_rejected()
    print("WEB URL SOURCE TESTS PASSED")
