"""
Auth router for SynApps Orchestrator.

Extracted from main.py (Step 3 of M-1 router decomposition).
"""
from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy import select

from apps.orchestrator.db import get_db_session
from apps.orchestrator.dependencies import (
    _api_key_lookup_prefix,
    _decode_token,
    _encrypt_api_key,
    _hash_password,
    _hash_sha256,
    _issue_api_tokens,
    _store_refresh_token,
    _utc_now,
    _verify_password,
    get_authenticated_user,
)
from apps.orchestrator.helpers import (
    API_KEY_VALUE_PREFIX,
    paginate,
)
from apps.orchestrator.models import (
    APIKeyCreateResponseModel,
    APIKeyResponseModel,
    AuthTokenResponseModel,
    UserProfileModel,
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
from apps.orchestrator.request_models import (
    APIKeyCreateRequestStrict,
    AuthLoginRequestStrict,
    AuthRefreshRequestStrict,
    AuthRegisterRequestStrict,
)

logger = logging.getLogger("orchestrator")


# Orchestrator and applet_registry are populated by main.py after all modules load.
# They start as None/empty and are set via _setup_router_globals() in main.py.
Orchestrator = None  # type: ignore[assignment]
applet_registry: dict = {}

router = APIRouter()


# ============================================================
# Auth Routes
# ============================================================

@router.post("/auth/register", response_model=AuthTokenResponseModel, status_code=201, tags=["Auth"])
async def register(body: AuthRegisterRequestStrict):
    """Register a new user account and receive JWT tokens."""
    now = _utc_now()
    async with get_db_session() as session:
        existing_result = await session.execute(
            select(AuthUser).where(AuthUser.email == body.email)
        )
        if existing_result.scalars().first():
            raise HTTPException(status_code=409, detail="Email already registered")

        user = AuthUser(
            id=str(uuid.uuid4()),
            email=body.email,
            password_hash=_hash_password(body.password),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(user)

    token_response, refresh_token, refresh_expires_at = _issue_api_tokens(user)
    await _store_refresh_token(user.id, refresh_token, refresh_expires_at)
    return token_response


@router.post("/auth/login", response_model=AuthTokenResponseModel, tags=["Auth"])
async def login(body: AuthLoginRequestStrict):
    """Authenticate with email/password and receive JWT tokens."""
    async with get_db_session() as session:
        user_result = await session.execute(select(AuthUser).where(AuthUser.email == body.email))
        user = user_result.scalars().first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not _verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user.updated_at = _utc_now()

    token_response, refresh_token, refresh_expires_at = _issue_api_tokens(user)
    await _store_refresh_token(user.id, refresh_token, refresh_expires_at)
    return token_response


@router.post("/auth/refresh", response_model=AuthTokenResponseModel, tags=["Auth"])
async def refresh_token(body: AuthRefreshRequestStrict):
    """Rotate a refresh token and receive a new access/refresh pair."""
    raw_refresh = body.refresh_token.strip()
    payload = _decode_token(raw_refresh, expected_type="refresh")
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token subject")

    refresh_hash = _hash_sha256(raw_refresh)
    now = _utc_now()

    async with get_db_session() as session:
        refresh_result = await session.execute(
            select(AuthRefreshToken).where(AuthRefreshToken.token_hash == refresh_hash)
        )
        stored_refresh = refresh_result.scalars().first()
        if not stored_refresh or stored_refresh.revoked:
            raise HTTPException(status_code=401, detail="Refresh token revoked")
        if stored_refresh.expires_at <= now:
            stored_refresh.revoked = True
            raise HTTPException(status_code=401, detail="Refresh token expired")
        if stored_refresh.user_id != user_id:
            raise HTTPException(status_code=401, detail="Refresh token user mismatch")

        user_result = await session.execute(select(AuthUser).where(AuthUser.id == user_id))
        user = user_result.scalars().first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User is not active")

        stored_refresh.revoked = True
        stored_refresh.last_used_at = now
        user.updated_at = now

    token_response, new_refresh_token, refresh_expires_at = _issue_api_tokens(user)
    await _store_refresh_token(user.id, new_refresh_token, refresh_expires_at)
    return token_response


@router.post("/auth/logout", tags=["Auth"])
async def logout(body: AuthRefreshRequestStrict):
    """Revoke a refresh token (log out)."""
    raw_refresh = body.refresh_token.strip()
    refresh_hash = _hash_sha256(raw_refresh)

    async with get_db_session() as session:
        refresh_result = await session.execute(
            select(AuthRefreshToken).where(AuthRefreshToken.token_hash == refresh_hash)
        )
        stored_refresh = refresh_result.scalars().first()
        if stored_refresh:
            stored_refresh.revoked = True
            stored_refresh.last_used_at = _utc_now()

    return {"message": "Logged out"}


@router.get("/auth/me", response_model=UserProfileModel, tags=["Auth"])
async def auth_me(current_user: dict[str, Any] = Depends(get_authenticated_user)):
    """Return the authenticated user's profile."""
    return UserProfileModel(
        id=current_user["id"],
        email=current_user["email"],
        is_active=current_user["is_active"],
        created_at=current_user["created_at"],
    )


@router.post("/auth/api-keys", response_model=APIKeyCreateResponseModel, status_code=201, tags=["Auth"])
async def create_api_key(
    body: APIKeyCreateRequestStrict,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Create an API key for X-API-Key header authentication."""
    plain_key = f"{API_KEY_VALUE_PREFIX}_{secrets.token_urlsafe(32)}"
    now = _utc_now()
    api_key_record = AuthUserAPIKey(
        id=str(uuid.uuid4()),
        user_id=current_user["id"],
        name=body.name,
        key_prefix=_api_key_lookup_prefix(plain_key),
        encrypted_key=_encrypt_api_key(plain_key),
        is_active=True,
        created_at=now,
        last_used_at=None,
    )

    async with get_db_session() as session:
        session.add(api_key_record)

    return APIKeyCreateResponseModel(
        id=api_key_record.id,
        name=api_key_record.name,
        key_prefix=api_key_record.key_prefix,
        is_active=api_key_record.is_active,
        created_at=api_key_record.created_at,
        last_used_at=api_key_record.last_used_at,
        api_key=plain_key,
    )


@router.get("/auth/api-keys", tags=["Auth"])
async def list_api_keys(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """List active API keys for the authenticated user."""
    async with get_db_session() as session:
        result = await session.execute(
            select(AuthUserAPIKey).where(
                AuthUserAPIKey.user_id == current_user["id"],
                AuthUserAPIKey.is_active == True,  # noqa: E712 - SQLAlchemy boolean comparison
            )
        )
        records = result.scalars().all()
        items = [
            APIKeyResponseModel(
                id=record.id,
                name=record.name,
                key_prefix=record.key_prefix,
                is_active=record.is_active,
                created_at=record.created_at,
                last_used_at=record.last_used_at,
            ).model_dump()
            for record in records
        ]
        return paginate(items, page, page_size)


@router.delete("/auth/api-keys/{api_key_id}", tags=["Auth"])
async def revoke_api_key(
    api_key_id: str,
    current_user: dict[str, Any] = Depends(get_authenticated_user),
):
    """Revoke a user API key."""
    async with get_db_session() as session:
        result = await session.execute(
            select(AuthUserAPIKey).where(
                AuthUserAPIKey.id == api_key_id,
                AuthUserAPIKey.user_id == current_user["id"],
            )
        )
        record = result.scalars().first()
        if not record:
            raise HTTPException(status_code=404, detail="API key not found")
        record.is_active = False
        record.last_used_at = _utc_now()

    return {"message": "API key revoked"}

