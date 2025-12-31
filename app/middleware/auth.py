"""
Authentication Middleware for FastAPI

Handles JWT token extraction and verification for authenticated routes.
"""

from typing import Optional
from dataclasses import dataclass
from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import config
from app.lib.supabase_client import verify_jwt_token, verify_token_with_supabase


@dataclass
class User:
    """Authenticated user data."""
    id: str
    email: str
    metadata: dict
    membership_tier: str = "free"


# Routes that don't require authentication
PUBLIC_ROUTES = [
    "/",
    "/login",
    "/signup",
    "/pricing",
    "/api/auth/magic-link",
    "/api/auth/callback",
    "/api/webhooks/stripe",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/static",
    "/favicon.ico",
]

# Routes that require authentication
PROTECTED_ROUTES = [
    "/dashboard",
    "/ingest",
    "/browse",
    "/query",
    "/chat",
    "/settings",
    "/status",
    "/account",
]


def is_public_route(path: str) -> bool:
    """Check if a route is public (doesn't require auth)."""
    # Check exact matches
    if path in PUBLIC_ROUTES:
        return True

    # Check prefix matches
    for route in PUBLIC_ROUTES:
        if path.startswith(route + "/") or path.startswith(route):
            return True

    # Static files are always public
    if path.startswith("/static"):
        return True

    return False


def is_protected_route(path: str) -> bool:
    """Check if a route requires authentication."""
    for route in PROTECTED_ROUTES:
        if path == route or path.startswith(route + "/"):
            return True
    return False


def extract_token(request: Request) -> Optional[str]:
    """
    Extract the JWT token from the request.

    Checks in order:
    1. Authorization header (Bearer token)
    2. Cookie (sb-access-token or access_token)

    Args:
        request: The FastAPI request object

    Returns:
        The JWT token if found, None otherwise
    """
    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]

    # Check cookies
    token = request.cookies.get("sb-access-token")
    if token:
        return token

    token = request.cookies.get("access_token")
    if token:
        return token

    return None


async def get_user_from_request(request: Request) -> Optional[User]:
    """
    Get the authenticated user from the request.

    Args:
        request: The FastAPI request object

    Returns:
        User object if authenticated, None otherwise
    """
    # Check if Supabase is configured
    if not config.supabase.is_configured:
        return None

    token = extract_token(request)
    if not token:
        return None

    # Verify the token
    payload = verify_jwt_token(token)
    if not payload:
        payload = verify_token_with_supabase(token)

    if not payload:
        return None

    # Extract user data
    user_id = payload.get("sub")
    email = payload.get("email", "")
    metadata = payload.get("user_metadata", {})

    if not user_id:
        return None

    # Get membership tier from app_metadata or default to free
    app_metadata = payload.get("app_metadata", {})
    membership_tier = app_metadata.get("membership_tier", "free")

    return User(
        id=user_id,
        email=email,
        metadata=metadata,
        membership_tier=membership_tier,
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that attaches user data to request state.

    For protected routes, redirects to login if not authenticated.
    For public routes, attaches user data if available (optional auth).
    """

    async def dispatch(self, request: Request, call_next):
        # Skip auth if Supabase not configured (development mode)
        if not config.supabase.is_configured:
            request.state.user = None
            return await call_next(request)

        # Get user from request
        user = await get_user_from_request(request)
        request.state.user = user

        # Check if route requires authentication
        path = request.url.path

        if is_protected_route(path) and user is None:
            # Redirect to login for web pages
            if not path.startswith("/api/"):
                return RedirectResponse(
                    url=f"/login?redirect={path}",
                    status_code=status.HTTP_302_FOUND
                )
            # Return 401 for API routes
            return HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)


async def get_current_user(request: Request) -> User:
    """
    Dependency to get the current authenticated user.

    Raises HTTPException if not authenticated.

    Usage:
        @app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user": user.email}
    """
    user = getattr(request.state, "user", None)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_optional_user(request: Request) -> Optional[User]:
    """
    Dependency to get the current user if authenticated.

    Returns None if not authenticated (doesn't raise exception).

    Usage:
        @app.get("/optional-auth")
        async def optional_auth_route(user: Optional[User] = Depends(get_optional_user)):
            if user:
                return {"user": user.email}
            return {"message": "Guest access"}
    """
    return getattr(request.state, "user", None)


def require_tier(min_tier: str):
    """
    Dependency factory to require a minimum membership tier.

    Args:
        min_tier: Minimum tier required ("free", "pro", "enterprise")

    Usage:
        @app.get("/pro-feature")
        async def pro_route(user: User = Depends(require_tier("pro"))):
            return {"message": "Pro feature access"}
    """
    tier_levels = {"free": 0, "pro": 1, "enterprise": 2}
    required_level = tier_levels.get(min_tier, 0)

    async def dependency(request: Request) -> User:
        user = await get_current_user(request)
        user_level = tier_levels.get(user.membership_tier, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires {min_tier} tier or higher",
            )

        return user

    return dependency
