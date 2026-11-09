"""Web URL validation for the browser-assisted audio source.

The app deliberately delegates sign-in to the user's default browser, so OAuth,
OIDC, MFA, SSO and the browser's existing sessions remain under the user's control.
The URL itself is never persisted by this module.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .settings import sanitize


def validate_web_url(value: str) -> tuple[bool, str]:
    """Return (valid, reason). Allow query authentication parameters, reject userinfo."""
    raw = (value or "").strip()
    if not raw:
        return False, "Enter a complete http:// or https:// URL."
    try:
        parts = urlsplit(raw)
        # Accessing .port also detects malformed ports.
        _ = parts.port
    except ValueError:
        return False, "The URL is malformed. Check its host and port."
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return False, "Use a complete http:// or https:// URL."
    if parts.username is not None or parts.password is not None:
        return False, "Remove username/password from the URL and sign in through the browser."
    return True, ""


def autoplay_url(value: str) -> tuple[str, str | None]:
    """Best-effort autoplay parameters for known video players.

    This asks the site to autoplay; browser gesture policies can still require
    a user click. Unknown providers are left untouched.
    """
    parts = urlsplit(value)
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.lower()
    provider = None
    if host in {"youtube.com", "m.youtube.com", "youtu.be"}:
        provider = "YouTube"
    elif host == "player.vimeo.com" and path.startswith("/video/"):
        provider = "Vimeo player"
    if provider is None:
        return value, None
    query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
             if key.casefold() != "autoplay"]
    query.append(("autoplay", "1"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query, doseq=True), parts.fragment)), provider


def url_recording_stem(index: int, title: str, base: str) -> str:
    """Filename stem for a playlist item; no URL/query credentials are included."""
    title = sanitize(str(title), fallback="Web audio")[:70]
    base = sanitize(str(base), fallback="Recording")
    return sanitize(f"{max(1, int(index) + 1):02d} - {title} - {base}")[:180]
