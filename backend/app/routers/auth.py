from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.deps import get_current_user
from app.core.ratelimit import (
    assert_not_locked_out,
    clear_failed_logins,
    consume_action_jti,
    enforce_rate_limit,
    register_failed_login,
)
from app.core.security import (
    create_access_token,
    create_action_token,
    create_refresh_token,
    decode_action_token_payload,
    decode_token,
    generate_totp_secret,
    get_totp_uri,
    hash_password,
    validate_password_strength,
    verify_password,
    verify_totp,
)
from app.models.user import AuditLog, User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    TokenResponse,
    UserCreate,
    UserOut,
    VerifyEmailRequest,
)
from app.services import auth_google
from app.services.email import send_password_reset_email, send_verification_email

router = APIRouter()

_settings = get_settings()
_logger = get_logger(__name__)


def _slug_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "workspace"


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, request: Request, db: AsyncSession = Depends(get_db)) -> User:
    await enforce_rate_limit(request, "register")

    problems = validate_password_strength(body.password)
    if problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password " + "; ".join(problems),
        )

    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # The first user on a fresh instance becomes the superuser (instance admin),
    # so a self-hosted deployment has someone who can configure AI/global settings.
    is_first = (await db.execute(select(func.count()).select_from(User))).scalar_one() == 0

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        is_superuser=is_first,
    )
    db.add(user)
    await db.flush()

    token = create_action_token(user.id, "email_verify", expires_minutes=60 * 24)
    await send_verification_email(user.email, token)

    db.add(AuditLog(user_id=user.id, action="user.register", resource_type="user", resource_id=user.id))
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    await enforce_rate_limit(request, "login")
    await assert_not_locked_out(body.email)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    # Google-only accounts have no local password (hashed_password is None).
    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        await register_failed_login(body.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    if _settings.require_email_verification and not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Check your inbox or request a new verification email.",
        )

    if user.totp_enabled:
        if not body.totp_code or not verify_totp(user.totp_secret, body.totp_code):
            await register_failed_login(body.email)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    await clear_failed_logins(body.email)

    db.add(AuditLog(
        user_id=user.id,
        action="user.login",
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    ))

    return {
        "access_token": create_access_token(user.id, token_version=user.token_version),
        "refresh_token": create_refresh_token(user.id, token_version=user.token_version),
        "token_type": "bearer",
    }


# ── Sign in with Google (OIDC) ────────────────────────────────────────────────

@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    """Kick off the Google sign-in flow. Redirects the browser to Google's consent
    screen; Google then redirects back to /auth/google/callback."""
    await enforce_rate_limit(request, "google_login")
    state = secrets.token_urlsafe(24)
    if auth_google.configured():
        target = auth_google.build_login_url(state)
    elif auth_google.dev_mock_enabled():
        # Local dev with no real Google creds: round-trip through our own callback
        # (same origin, relative URL) with a mock code instead of hitting Google.
        target = f"/api/auth/google/callback?code={auth_google.DEV_MOCK_CODE}&state={state}"
    else:
        return RedirectResponse(f"{_settings.frontend_url}/auth/login?error=google_not_configured")
    resp = RedirectResponse(target)
    # CSRF: bind the OAuth state to this browser via a short-lived cookie we verify
    # on callback (SameSite=Lax so it survives Google's top-level redirect back).
    resp.set_cookie(
        "g_oauth_state", state, max_age=900, httponly=True, samesite="lax",
        secure=_settings.environment != "development",  # Secure on staging + production
    )
    return resp


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Google redirects here with ?code. Exchange it, find-or-create the user, then
    hand the browser our own JWTs via the frontend /auth/callback page."""
    await enforce_rate_limit(request, "google_callback")
    login_url = f"{_settings.frontend_url}/auth/login"
    if error or not code:
        return RedirectResponse(f"{login_url}?error=google_failed")

    cookie_state = request.cookies.get("g_oauth_state")
    if not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        return RedirectResponse(f"{login_url}?error=google_state")

    if code == auth_google.DEV_MOCK_CODE and auth_google.dev_mock_enabled():
        profile = auth_google.mock_profile()  # local dev — no external call
    else:
        try:
            profile = await auth_google.exchange_code(code)
        except Exception as exc:  # network / bad code / Google error — fail closed
            _logger.warning("Google OIDC exchange failed: %s", exc)
            return RedirectResponse(f"{login_url}?error=google_failed")

    try:
        # 1) match by Google id, 2) link to an existing email account, 3) create new
        user = (await db.execute(select(User).where(User.google_id == profile["sub"]))).scalar_one_or_none()
        if not user:
            user = (await db.execute(select(User).where(User.email == profile["email"]))).scalar_one_or_none()
            if user:
                # Only auto-link to an existing account when Google has VERIFIED the email —
                # otherwise an attacker with an unverified Google account bearing the victim's
                # address could take over the account.
                if not profile["email_verified"]:
                    return RedirectResponse(f"{login_url}?error=google_unverified")
                # Don't silently rebind a different Google identity onto this account.
                if user.google_id and user.google_id != profile["sub"]:
                    return RedirectResponse(f"{login_url}?error=google_account_conflict")
                user.google_id = profile["sub"]
                user.email_verified = True
                user.auth_provider = "google"
                db.add(AuditLog(user_id=user.id, action="user.link_google", resource_type="user", resource_id=user.id))
            else:
                is_first = (await db.execute(select(func.count()).select_from(User))).scalar_one() == 0
                user = User(
                    email=profile["email"],
                    full_name=profile["name"],
                    google_id=profile["sub"],
                    auth_provider="google",
                    hashed_password=None,
                    email_verified=profile["email_verified"],
                    # Bootstrap superuser only when Google vouches for the email.
                    is_superuser=is_first and profile["email_verified"],
                )
                db.add(user)
                await db.flush()
                db.add(AuditLog(user_id=user.id, action="user.register_google", resource_type="user", resource_id=user.id))

        await db.flush()  # persist account-link / creation before issuing tokens
    except IntegrityError:
        # Concurrent first-login for the same identity — the other request won the
        # unique constraint. Recover by loading the row it created.
        await db.rollback()
        user = (await db.execute(select(User).where(User.google_id == profile["sub"]))).scalar_one_or_none()
        if not user:
            return RedirectResponse(f"{login_url}?error=google_failed")

    if not user.is_active:
        return RedirectResponse(f"{login_url}?error=account_disabled")

    db.add(AuditLog(
        user_id=user.id, action="user.login_google", resource_type="user", resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    ))

    access = create_access_token(user.id, token_version=user.token_version)
    refresh = create_refresh_token(user.id, token_version=user.token_version)
    # Tokens in the URL fragment (#) so they never reach server logs or the Referer header.
    resp = RedirectResponse(
        f"{_settings.frontend_url}/auth/callback#access_token={access}&refresh_token={refresh}"
    )
    resp.delete_cookie("g_oauth_state")
    return resp


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        user_id, jti = decode_action_token_payload(body.token, "email_verify")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification link")

    if not await consume_action_jti(jti, ttl_seconds=60 * 60 * 24):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This verification link has already been used")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    user.email_verified = True
    db.add(AuditLog(user_id=user.id, action="user.email_verified", resource_type="user", resource_id=user.id))
    await db.flush()
    return {"verified": True}


@router.post("/resend-verification")
async def resend_verification(
    body: ResendVerificationRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    await enforce_rate_limit(request, "resend_verification", per_minute=3)
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    # Always return success to avoid leaking which emails are registered
    if user and not user.email_verified:
        token = create_action_token(user.id, "email_verify", expires_minutes=60 * 24)
        await send_verification_email(user.email, token)
    return {"sent": True}


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    await enforce_rate_limit(request, "forgot_password", per_minute=3)
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    # Always return success to avoid leaking which emails are registered
    if user:
        token = create_action_token(user.id, "password_reset", expires_minutes=60)
        await send_password_reset_email(user.email, token)
        db.add(AuditLog(user_id=user.id, action="user.password_reset_requested", resource_type="user", resource_id=user.id))
    return {"sent": True}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    await enforce_rate_limit(request, "reset_password", per_minute=5)
    try:
        user_id, jti = decode_action_token_payload(body.token, "password_reset")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link")

    problems = validate_password_strength(body.new_password)
    if problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password " + "; ".join(problems),
        )

    # Single-use: reject a reset token that has already been redeemed.
    if not await consume_action_jti(jti, ttl_seconds=60 * 60):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This reset link has already been used")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    user.hashed_password = hash_password(body.new_password)
    # Bump the credential epoch so every previously-issued access/refresh token
    # for this user is rejected — a password reset terminates all old sessions.
    user.token_version = (user.token_version or 0) + 1
    await clear_failed_logins(user.email)
    db.add(AuditLog(user_id=user.id, action="user.password_reset", resource_type="user", resource_id=user.id))
    await db.flush()
    return {"reset": True}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        payload = decode_token(body.refresh_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Reject refresh tokens minted before the last password reset.
    if payload.get("tv", 0) != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token no longer valid; please sign in again")

    return {
        "access_token": create_access_token(user.id, token_version=user.token_version),
        "refresh_token": create_refresh_token(user.id, token_version=user.token_version),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/mfa/setup", response_model=TOTPSetupResponse)
async def setup_mfa(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    secret = generate_totp_secret()
    user.totp_secret = secret
    await db.flush()
    return {"secret": secret, "uri": get_totp_uri(secret, user.email)}


@router.post("/mfa/verify")
async def verify_mfa(
    body: TOTPVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA not set up")
    if not verify_totp(user.totp_secret, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code")
    user.totp_enabled = True
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="user.mfa.enabled", resource_type="user", resource_id=user.id))
    return {"enabled": True}


@router.delete("/mfa/disable")
async def disable_mfa(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user.totp_enabled = False
    user.totp_secret = None
    await db.flush()
    return {"disabled": True}
