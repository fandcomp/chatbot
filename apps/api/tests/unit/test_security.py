import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_and_verify_password_succeeds_for_correct_password() -> None:
    # Arrange
    password = "correct-horse-battery-staple"

    # Act
    hashed = hash_password(password)

    # Assert
    assert hashed != password
    assert verify_password(password, hashed) is True


def test_verify_password_fails_for_wrong_password() -> None:
    # Arrange
    hashed = hash_password("correct-horse-battery-staple")

    # Act / Assert
    assert verify_password("wrong-password", hashed) is False


def test_create_access_token_and_decode_access_token_round_trips_claims() -> None:
    # Arrange
    data = {"sub": "user-id-123"}

    # Act
    token = create_access_token(data)
    payload = decode_access_token(token)

    # Assert
    assert payload["sub"] == "user-id-123"
    assert "exp" in payload


def test_decode_access_token_rejects_expired_token() -> None:
    # Arrange
    token = create_access_token({"sub": "user-id-123"}, expires_minutes=-1)

    # Act / Assert
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_decode_access_token_rejects_tampered_token() -> None:
    # Arrange
    token = create_access_token({"sub": "user-id-123"})
    tampered = token[:-4] + ("A" if token[-4] != "A" else "B") + token[-3:]

    # Act / Assert
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(tampered)


def test_decode_access_token_rejects_token_signed_with_wrong_secret() -> None:
    # Arrange
    forged = jwt.encode({"sub": "user-id-123"}, "not-the-real-secret", algorithm="HS256")

    # Act / Assert
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)
