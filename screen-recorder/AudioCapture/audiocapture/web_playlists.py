"""Safe persistence for named URL playlists (never store URL credentials/tokens)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .settings import sanitize, settings_path
from .url_source import validate_web_url

_SENSITIVE_EXACT = {
    "token", "accesstoken", "refreshtoken", "idtoken", "auth", "authorization",
    "apikey", "key", "secret", "clientsecret", "password", "passwd",
    "signature", "sig", "session", "sessionid", "code", "state", "credential", "jwt",
}
_SENSITIVE_PARTS = ("token", "secret", "password", "passwd", "signature", "credential", "session", "authorization", "jwt")


def is_sensitive_parameter(key: str) -> bool:
    norm = re.sub(r"[^a-z0-9]", "", key.casefold())
    return norm in _SENSITIVE_EXACT or any(part in norm for part in _SENSITIVE_PARTS)


def sanitize_url_for_storage(url: str) -> tuple[str, int]:
    """Strip userinfo and sensitive query/fragment keys; preserve benign URL parameters."""
    valid, reason = validate_web_url(url)
    if not valid:
        raise ValueError(reason)
    parts = urlsplit(url.strip())
    query = parse_qsl(parts.query, keep_blank_values=True)
    safe_query = [(k, v) for k, v in query if not is_sensitive_parameter(k)]
    removed = len(query) - len(safe_query)

    # OAuth implicit-flow tokens sometimes live in the URL fragment.
    fragment_pairs = parse_qsl(parts.fragment, keep_blank_values=True)
    if fragment_pairs:
        safe_fragment = [(k, v) for k, v in fragment_pairs if not is_sensitive_parameter(k)]
        removed += len(fragment_pairs) - len(safe_fragment)
        fragment = urlencode(safe_fragment, doseq=True)
    elif any(term in parts.fragment.casefold() for term in ("token", "secret", "password", "auth")):
        fragment = ""
        removed += 1
    else:
        fragment = parts.fragment

    safe = urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(safe_query, doseq=True), fragment))
    return safe, removed


def playlist_store_path() -> Path:
    return settings_path().parent / "web_playlists.json"


def load_saved_playlists(path: str | os.PathLike | None = None) -> dict[str, list[str]]:
    source = Path(path) if path is not None else playlist_store_path()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        result: dict[str, list[str]] = {}
        for name, urls in payload.items():
            if not isinstance(name, str) or not isinstance(urls, list):
                continue
            safe_urls = []
            for url in urls:
                if isinstance(url, str):
                    try:
                        safe, _ = sanitize_url_for_storage(url)
                        if safe:
                            safe_urls.append(safe)
                    except ValueError:
                        continue
            if safe_urls:
                result[name] = safe_urls
        return result
    except (OSError, ValueError, TypeError):
        return {}


def save_playlist(name: str, urls: list[str], path: str | os.PathLike | None = None) -> tuple[str, int]:
    """Save a named sanitized playlist. Returns (stored_name, removed_secret_count)."""
    stored_name = sanitize(name, fallback="Playlist")[:60]
    if not urls:
        raise ValueError("The playlist is empty.")
    clean_urls: list[str] = []
    removed = 0
    for url in urls:
        safe, count = sanitize_url_for_storage(url)
        clean_urls.append(safe)
        removed += count
    store = Path(path) if path is not None else playlist_store_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    data = load_saved_playlists(store)
    data[stored_name] = clean_urls
    temp = store.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    os.replace(temp, store)
    return stored_name, removed
