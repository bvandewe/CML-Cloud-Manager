"""Unit tests for AuthService covering RS256 verification, HS256 fallback, issuer/audience checks, and role mapping.

These tests mock JWKS retrieval and generate tokens with PyJWT.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest

from api.services.auth import DualAuthService
from application.settings import app_settings
from infrastructure import InMemorySessionStore


class DummySessionStore(InMemorySessionStore):
    pass


@pytest.fixture()
def session_store():
    return DummySessionStore(session_timeout_hours=1)


@pytest.fixture()
def auth_service(session_store):
    return DualAuthService(session_store)


def generate_rs256_keys():
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    from jwt.algorithms import RSAAlgorithm

    jwk = RSAAlgorithm.to_jwk(public_key)
    jwk_dict = json.loads(jwk)
    jwk_dict["kid"] = "test-kid"
    return private_key, jwk_dict


def build_rs256_token(private_key, kid: str, claims: dict[str, Any]):
    headers = {"alg": "RS256", "kid": kid, "typ": "JWT"}
    return jwt.encode(claims, private_key, algorithm="RS256", headers=headers)


def test_rs256_success(monkeypatch, auth_service):
    private_key, jwk_dict = generate_rs256_keys()

    # Mock JWKS fetch
    monkeypatch.setattr(
        auth_service, "_fetch_jwks", lambda: {"keys": [jwk_dict], "fetched_at": 0}
    )

    claims = {
        "sub": "user123",
        "preferred_username": "alice",
        "realm_access": {"roles": ["user", "manager"]},
        "iss": "expected-iss",
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=5),
    }
    token = build_rs256_token(private_key, jwk_dict["kid"], claims)

    # Disable strict validation for this test
    monkeypatch.setattr(app_settings, "VERIFY_ISSUER", False)
    monkeypatch.setattr(app_settings, "VERIFY_AUDIENCE", False)

    user = auth_service.get_user_from_jwt(token)
    if user is None:
        pytest.fail("Expected authenticated user for valid RS256 token")
    if user.get("username") != "alice":
        pytest.fail("Expected username 'alice'")
    if "manager" not in user.get("roles", []):
        pytest.fail("Expected 'manager' role to be present")
    if user.get("legacy") is not False:
        pytest.fail("Expected legacy flag to be False for RS256 token")


def test_rs256_issuer_mismatch(monkeypatch, auth_service):
    private_key, jwk_dict = generate_rs256_keys()
    monkeypatch.setattr(
        auth_service, "_fetch_jwks", lambda: {"keys": [jwk_dict], "fetched_at": 0}
    )

    claims = {
        "sub": "user123",
        "preferred_username": "alice",
        "realm_access": {"roles": ["user"]},
        "iss": "wrong-iss",
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=5),
    }
    token = build_rs256_token(private_key, jwk_dict["kid"], claims)

    monkeypatch.setattr(app_settings, "VERIFY_ISSUER", True)
    monkeypatch.setattr(app_settings, "EXPECTED_ISSUER", "expected-iss")

    user = auth_service.get_user_from_jwt(token)
    if user is not None:
        pytest.fail("Issuer mismatch should reject the token")


def test_hs256_fallback(monkeypatch, auth_service):
    # Create HS256 token with legacy secret
    claims = {
        "sub": "legacy1",
        "username": "legacy-user",
        "roles": ["user"],
        "exp": datetime.utcnow() + timedelta(minutes=5),
    }
    token = jwt.encode(
        claims, app_settings.jwt_secret_key, algorithm=app_settings.jwt_algorithm
    )

    user = auth_service.get_user_from_jwt(token)
    if user is None:
        pytest.fail("Expected user for HS256 fallback token")
    if user.get("legacy") is not True:
        pytest.fail("Legacy flag should be True for HS256 token")


def test_invalid_signature_rs256(monkeypatch, auth_service):
    # RS256 token signed with one key but JWKS returns different key
    priv1, jwk1 = generate_rs256_keys()
    priv2, jwk2 = generate_rs256_keys()

    token = build_rs256_token(
        priv1,
        jwk1["kid"],
        {
            "sub": "user123",
            "preferred_username": "alice",
            "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=5),
        },
    )

    # JWKS returns unrelated key (different kid)
    monkeypatch.setattr(
        auth_service, "_fetch_jwks", lambda: {"keys": [jwk2], "fetched_at": 0}
    )

    user = auth_service.get_user_from_jwt(token)
    if user is not None:
        pytest.fail("Invalid signature should return no user")


def test_expired_rs256_token(monkeypatch, auth_service):
    private_key, jwk_dict = generate_rs256_keys()
    monkeypatch.setattr(
        auth_service, "_fetch_jwks", lambda: {"keys": [jwk_dict], "fetched_at": 0}
    )
    claims = {
        "sub": "user123",
        "preferred_username": "alice",
        "exp": datetime.now(tz=timezone.utc) - timedelta(seconds=10),  # already expired
    }
    token = build_rs256_token(private_key, jwk_dict["kid"], claims)
    user = auth_service.get_user_from_jwt(token)
    if user is not None:
        pytest.fail("Expired token must not authenticate user")


def test_audience_mismatch_rs256(monkeypatch, auth_service):
    private_key, jwk_dict = generate_rs256_keys()
    monkeypatch.setattr(
        auth_service, "_fetch_jwks", lambda: {"keys": [jwk_dict], "fetched_at": 0}
    )
    monkeypatch.setattr(app_settings, "VERIFY_AUDIENCE", True)
    monkeypatch.setattr(
        app_settings, "EXPECTED_AUDIENCE", ["expected-aud"]
    )  # enforce audience
    claims = {
        "sub": "user123",
        "preferred_username": "alice",
        "aud": ["wrong-aud"],
        "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=5),
    }
    token = build_rs256_token(private_key, jwk_dict["kid"], claims)
    user = auth_service.get_user_from_jwt(token)
    # Since we enforce audience and token aud mismatches, should return None
    if user is not None:
        pytest.fail("Audience mismatch should invalidate token")
    # Reset audience enforcement for other tests
    monkeypatch.setattr(app_settings, "VERIFY_AUDIENCE", False)
    monkeypatch.setattr(app_settings, "EXPECTED_AUDIENCE", [])
