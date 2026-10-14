"""Authentication endpoints for SupportGPT AI."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import extract_session_token, get_current_user
from app.core.errors import AuthenticationException
from app.core.logging import get_logger
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    needs_rehash,
    normalize_email,
    verify_password,
)
from app.db.session import get_db_session
from app.models.enums import MembershipStatus, UserStatus
from app.models.membership import OrganizationMembership
from app.models.session import UserSession
from app.models.user import User
from app.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    UserOrganizationSummary,
    UserResponse,
)

logger = get_logger("supportgpt.auth")
router = APIRouter(prefix="/auth", tags=["Authentication"])

# Dummy hash used to equalize execution time when an account does not exist (prevents timing attacks)
_DUMMY_ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHRzb21lc2FsdA$Y4qP2h4m2/4qR2/1x4G7u2j8d3x9w8Z1r0t9y8u7v6w"


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and issue session",
)
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    """Authenticate via email and password, establishing an HttpOnly session."""
    try:
        normalized_email = normalize_email(login_data.email)
    except ValueError:
        raise AuthenticationException("Invalid email or password.") from None

    # Query user by normalized email
    query = (
        select(User)
        .options(
            selectinload(User.memberships).selectinload(OrganizationMembership.organization)
        )
        .where(User.email == normalized_email)
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        # Constant-time dummy check to prevent email enumeration timing side-channels
        verify_password(login_data.password, _DUMMY_ARGON2_HASH)
        logger.warning(f"Failed login attempt for nonexistent user: {normalized_email}")
        raise AuthenticationException("Invalid email or password.")

    if not verify_password(login_data.password, user.password_hash):
        logger.warning(f"Invalid password attempt for user: {user.id}")
        raise AuthenticationException("Invalid email or password.")

    if user.status != UserStatus.ACTIVE:
        logger.warning(f"Login denied for inactive user: {user.id} (status={user.status})")
        raise AuthenticationException("User account is inactive or disabled.")

    # Rehash password if algorithm parameters have changed
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(login_data.password)

    # Update user audit timestamps
    user.last_login_at = datetime.now(UTC)

    # Create new server-managed revocable session
    session_token = generate_session_token()
    token_hash = hash_session_token(session_token)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.SESSION_DURATION_SECONDS)

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    if user_agent and len(user_agent) > 500:
        user_agent = user_agent[:500]

    user_session = UserSession(
        user_id=user.id,
        session_token_hash=token_hash,
        ip_address=client_ip,
        user_agent=user_agent,
        expires_at=expires_at,
    )
    db.add(user_session)
    await db.flush()

    # Set secure HttpOnly session cookie
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        max_age=settings.SESSION_DURATION_SECONDS,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        secure=settings.SESSION_COOKIE_SECURE or settings.ENVIRONMENT in ("staging", "production"),
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/",
    )

    # Collect available active organizations
    org_summaries: list[UserOrganizationSummary] = []
    for m in user.memberships:
        if m.status == MembershipStatus.ACTIVE and m.organization and m.organization.deleted_at is None:
            org_summaries.append(
                UserOrganizationSummary(
                    organization_id=m.organization_id,
                    name=m.organization.name,
                    slug=m.organization.slug,
                    role=m.role,
                    status=m.status,
                )
            )

    logger.info(f"User authenticated successfully: {user.id}")

    return LoginResponse(
        user=UserResponse.model_validate(user),
        expires_at=expires_at,
        token=session_token,
        organizations=org_summaries,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke active user session",
)
async def logout(
    response: Response,
    session_token: str | None = Depends(extract_session_token),
    db: AsyncSession = Depends(get_db_session),
) -> LogoutResponse:
    """Invalidate current session in database and clear session cookie."""
    if session_token:
        token_hash = hash_session_token(session_token)
        query = select(UserSession).where(UserSession.session_token_hash == token_hash)
        result = await db.execute(query)
        session_record = result.scalar_one_or_none()
        if session_record and session_record.is_active:
            session_record.revoke()
            logger.info(f"User session revoked: {session_record.id}")

    # Clear cookie
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
    )

    return LogoutResponse()


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve authenticated user profile and memberships",
)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> CurrentUserResponse:
    """Return identity profile and accessible organizations for the caller."""
    query = (
        select(OrganizationMembership)
        .options(selectinload(OrganizationMembership.organization))
        .where(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
        )
    )
    result = await db.execute(query)
    memberships = result.scalars().all()

    org_summaries: list[UserOrganizationSummary] = [
        UserOrganizationSummary(
            organization_id=m.organization_id,
            name=m.organization.name,
            slug=m.organization.slug,
            role=m.role,
            status=m.status,
        )
        for m in memberships
        if m.organization and m.organization.deleted_at is None
    ]

    return CurrentUserResponse(
        user=UserResponse.model_validate(current_user),
        organizations=org_summaries,
    )
