"""Unit tests for the M15 rate-limit key function (spec §95: tenant/user/IP/
endpoint) — chat and Test Knowledge are keyed by user_id when available,
not just IP, so users behind a shared office/NAT IP get separate budgets.
"""

from starlette.requests import Request

from app.auth.router import user_or_ip_key
from app.core.config import settings
from app.core.security import create_access_token


def _make_request(cookie_header: str | None = None, client_host: str = "203.0.113.5") -> Request:
    headers = [(b"cookie", cookie_header.encode())] if cookie_header else []
    scope = {"type": "http", "headers": headers, "client": (client_host, 12345)}
    return Request(scope)


def test_returns_user_key_for_a_valid_session_cookie() -> None:
    # Arrange
    token = create_access_token({"sub": "11111111-1111-1111-1111-111111111111"})
    request = _make_request(f"{settings.SESSION_COOKIE_NAME}={token}")

    # Act
    key = user_or_ip_key(request)

    # Assert
    assert key == "user:11111111-1111-1111-1111-111111111111"


def test_falls_back_to_ip_when_no_session_cookie_present() -> None:
    # Arrange
    request = _make_request(cookie_header=None, client_host="198.51.100.7")

    # Act / Assert
    assert user_or_ip_key(request) == "198.51.100.7"


def test_falls_back_to_ip_for_an_invalid_token() -> None:
    # Arrange — garbage value, not a real JWT.
    request = _make_request(f"{settings.SESSION_COOKIE_NAME}=not-a-real-token", client_host="198.51.100.9")

    # Act / Assert
    assert user_or_ip_key(request) == "198.51.100.9"
