"""
Authentication dependencies and JWT/Fernet utilities for SynApps Orchestrator.

Extracted from main.py (Step 2 of M-1 router decomposition).
"""

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
import uuid
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Header, HTTPException
from sqlalchemy import select

from apps.orchestrator.api_keys.manager import api_key_manager
from apps.orchestrator.db import get_db_session
from apps.orchestrator.models import (
    AuthTokenResponseModel,
)
from apps.orchestrator.models import (
    RefreshToken as AuthRefreshToken,
)
from apps.orchestrator.models import (
    User as AuthUser,
)
from apps.orchestrator.models import (
    UserAPIKey as AuthUserAPIKey,
)
from apps.orchestrator.stores import admin_key_registry

logger = logging.getLogger("orchestrator")

# ============================================================
# JWT / Auth Constants
# ============================================================

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "synapps-dev-jwt-secret-change-me")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("JWT_REFRESH_EXPIRE_DAYS", "14"))
PASSWORD_HASH_ITERATIONS = int(os.environ.get("PASSWORD_HASH_ITERATIONS", "390000"))
API_KEY_LOOKUP_PREFIX_LEN = int(os.environ.get("API_KEY_LOOKUP_PREFIX_LEN", "18"))
ALLOW_ANONYMOUS_WHEN_NO_USERS = os.environ.get(
    "ALLOW_ANONYMOUS_WHEN_NO_USERS",
    "true",
).strip().lower() in {"1", "true", "yes"}


# ============================================================
# Fernet Cipher Setup
# ============================================================


def _derive_fernet_key() -> bytes:
    configured = os.environ.get("FERNET_KEY", "").strip()
    if configured:
        try:
            return configured.encode("utf-8")
        except Exception:
            logger.warning("Invalid FERNET_KEY value; falling back to derived key")
    digest = hashlib.sha256(JWT_SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


FERNET_CIPHER = Fernet(_derive_fernet_key())


# ============================================================
# Authentication Utilities
# ============================================================


def _utc_now() -> float:
    return time.time()


def _hash_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _encrypt_api_key(plain_value: str) -> str:
    return FERNET_CIPHER.encrypt(plain_value.encode("utf-8")).decode("utf-8")


def _decrypt_api_key(encrypted_value: str) -> str | None:
    try:
        return FERNET_CIPHER.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    salt_text = base64.urlsafe_b64encode(salt).decode("utf-8")
    hash_text = base64.urlsafe_b64encode(digest).decode("utf-8")
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt_text}${hash_text}"


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, raw_iterations, salt_text, hash_text = password_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(raw_iterations)
        salt = base64.urlsafe_b64decode(salt_text.encode("utf-8"))
        expected = base64.urlsafe_b64decode(hash_text.encode("utf-8"))
    except Exception:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate, expected)


def _create_access_token(user: AuthUser) -> tuple[str, int]:
    now = int(_utc_now())
    expiry = now + ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = {
        "sub": user.id,
        "email": user.email,
        "token_type": "access",
        "iat": now,
        "exp": expiry,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, expiry - now


def _create_refresh_token(user: AuthUser) -> tuple[str, float, int]:
    now = int(_utc_now())
    expiry = now + REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    payload = {
        "sub": user.id,
        "email": user.email,
        "token_type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expiry,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, float(expiry), expiry - now


def _decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(status_code=401, detail="Token expired") from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err

    token_type = payload.get("token_type")
    if token_type != expected_type:
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


def _issue_api_tokens(user: AuthUser) -> tuple[AuthTokenResponseModel, str, float]:
    access_token, access_expires_in = _create_access_token(user)
    refresh_token, refresh_expires_at, refresh_expires_in = _create_refresh_token(user)
    response_payload = AuthTokenResponseModel(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        access_expires_in=access_expires_in,
        refresh_expires_in=refresh_expires_in,
    )
    return response_payload, refresh_token, refresh_expires_at


def _normalize_key_header_value(raw_value: str) -> str:
    return raw_value.strip()


def _api_key_lookup_prefix(api_key_value: str) -> str:
    return api_key_value[:API_KEY_LOOKUP_PREFIX_LEN]


def _user_to_principal(user: AuthUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "created_at": user.created_at,
    }


async def _store_refresh_token(
    user_id: str,
    refresh_token: str,
    expires_at: float,
) -> None:
    token_hash = _hash_sha256(refresh_token)
    async with get_db_session() as session:
        session.add(
            AuthRefreshToken(
                id=str(uuid.uuid4()),
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
                revoked=False,
                created_at=_utc_now(),
                last_used_at=None,
            )
        )


async def _authenticate_user_by_jwt(access_token: str) -> dict[str, Any]:
    payload = _decode_token(access_token, expected_type="access")
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Invalid access token subject")

    async with get_db_session() as session:
        result = await session.execute(select(AuthUser).where(AuthUser.id == user_id))
        user = result.scalars().first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User is not active")
        return _user_to_principal(user)


async def _authenticate_user_by_api_key(api_key_value: str) -> dict[str, Any]:
    normalized_key = _normalize_key_header_value(api_key_value)
    if not normalized_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    lookup_prefix = _api_key_lookup_prefix(normalized_key)

    async with get_db_session() as session:
        query = select(AuthUserAPIKey).where(
            AuthUserAPIKey.is_active == True,  # noqa: E712 - SQLAlchemy boolean comparison
            AuthUserAPIKey.key_prefix == lookup_prefix,
        )
        result = await session.execute(query)
        candidates = result.scalars().all()

        for credential in candidates:
            plain_key = _decrypt_api_key(credential.encrypted_key)
            if plain_key is None:
                continue
            if not hmac.compare_digest(plain_key, normalized_key):
                continue

            user_result = await session.execute(
                select(AuthUser).where(AuthUser.id == credential.user_id)
            )
            user = user_result.scalars().first()
            if not user or not user.is_active:
                break

            credential.last_used_at = _utc_now()
            return _user_to_principal(user)

    raise HTTPException(status_code=401, detail="Invalid API key")


async def _can_use_anonymous_bootstrap() -> bool:
    if not ALLOW_ANONYMOUS_WHEN_NO_USERS:
        return False
    try:
        async with get_db_session() as session:
            result = await session.execute(select(AuthUser.id).limit(1))
            first_user_id = result.scalar_one_or_none()
            return first_user_id is None
    except Exception:
        # Allow bootstrap traffic before auth tables are initialized.
        return True


async def get_authenticated_user(
    authorization: str | None = Header(None, alias="Authorization"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> dict[str, Any]:
    if x_api_key:
        stripped = x_api_key.strip()
        # Recognise admin API keys (sk- prefix) from the in-memory registry
        if stripped.startswith("sk-"):
            admin_key = admin_key_registry.validate_key(stripped)
            if admin_key:
                return {
                    "id": f"admin-key:{admin_key['id']}",
                    "email": f"admin-key@{admin_key['name']}",
                    "is_active": True,
                    "scopes": admin_key.get("scopes", []),
                    "created_at": admin_key.get("created_at"),
                }
            # Try managed key registry (Fernet-encrypted)
            managed_key = api_key_manager.validate(stripped)
            if managed_key:
                return {
                    "id": f"managed-key:{managed_key['id']}",
                    "email": f"managed-key@{managed_key['name']}",
                    "is_active": True,
                    "scopes": managed_key.get("scopes", []),
                    "rate_limit": managed_key.get("rate_limit"),
                    "tier": "enterprise",
                    "created_at": managed_key.get("created_at"),
                }
        return await _authenticate_user_by_api_key(stripped)

    if authorization:
        auth_text = authorization.strip()
        if auth_text.lower().startswith("bearer "):
            return await _authenticate_user_by_jwt(auth_text[7:].strip())
        if auth_text.lower().startswith("apikey "):
            return await _authenticate_user_by_api_key(auth_text[7:].strip())

    if await _can_use_anonymous_bootstrap():
        return {
            "id": "anonymous",
            "email": "anonymous@local",
            "is_active": True,
            "created_at": _utc_now(),
        }

    raise HTTPException(status_code=401, detail="Authentication required")
