"""Stored playlists discard all query/fragment data to avoid persisting tokens."""
import sys
from pathlib import Path
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audiocapture.web_playlists import (
    load_saved_playlists, save_playlist, sanitize_url_for_storage,
)


def test_all_query_and_fragment_data_are_removed():
    url = "https://www.youtube.com/watch?v=abc&list=xyz&access_token=secret#t=12&session_id=secret"
    safe, removed = sanitize_url_for_storage(url)
    assert safe == "https://www.youtube.com/watch"
    assert "secret" not in safe and "abc" not in safe
    assert removed == 1


def test_named_playlist_round_trip_is_sanitized():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "playlists.json"
        name, removed = save_playlist(
            "Music favorites", ["https://example.test/play?id=7&token=one"], path=path)
        assert name == "Music favorites" and removed == 1
        raw = path.read_text()
        assert "one" not in raw and "token" not in raw
        saved = load_saved_playlists(path)
        assert saved[name] == ["https://example.test/play?id=7"]


def test_username_password_is_never_saved():
    try:
        sanitize_url_for_storage("https://alice:pw@example.test/a")
    except ValueError:
        pass
    else:
        raise AssertionError("user:password URL was accepted")


if __name__ == "__main__":
    test_auth_query_and_fragment_are_removed_but_youtube_params_stay()
    test_named_playlist_round_trip_is_sanitized()
    test_username_password_is_never_saved()
    print("SAFE WEB PLAYLIST TESTS PASSED")
