"""
Authentication API Endpoints

Provides endpoints for user authentication via Supabase.
"""

from typing import Optional
from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, EmailStr

from app.config import config
from app.lib.supabase_client import get_supabase_client, get_user_profile
from app.middleware.auth import get_current_user, get_optional_user, User

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class MagicLinkRequest(BaseModel):
    """Request body for sending magic link."""
    email: EmailStr
    redirect: Optional[str] = None


class MagicLinkResponse(BaseModel):
    """Response for magic link request."""
    success: bool
    message: str


class UserResponse(BaseModel):
    """Response containing user data."""
    id: str
    email: str
    membership_tier: str
    profile: Optional[dict] = None


class OAuthResponse(BaseModel):
    """Response for OAuth initiation."""
    url: str


@router.get("/google")
async def google_auth(request: Request, redirect: Optional[str] = None):
    """
    Initiate Google OAuth sign-in flow.

    Redirects the user to Google's OAuth consent screen.
    After authentication, user is redirected back to /api/auth/callback.
    """
    if not config.supabase.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured"
        )

    try:
        client = get_supabase_client()

        # Build callback URL
        origin = request.headers.get("origin") or request.headers.get("host")
        if origin and not origin.startswith("http"):
            # Check if we're behind a proxy with X-Forwarded headers
            proto = request.headers.get("x-forwarded-proto", "http")
            origin = f"{proto}://{origin}"
        elif not origin:
            origin = "http://localhost:8200"

        callback_url = f"{origin}/api/auth/callback"
        if redirect:
            callback_url += f"?next={redirect}"

        # Initiate OAuth flow
        response = client.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": callback_url,
                "scopes": "email profile",
            }
        })

        if response.url:
            return RedirectResponse(url=response.url, status_code=status.HTTP_302_FOUND)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate Google OAuth"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth error: {str(e)}"
        )


@router.post("/magic-link", response_model=MagicLinkResponse)
async def send_magic_link(request: Request, data: MagicLinkRequest):
    """
    Send a magic link to the user's email for passwordless authentication.

    This handles both sign-up and sign-in - if the email doesn't exist,
    a new account is created automatically.
    """
    if not config.supabase.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured"
        )

    try:
        client = get_supabase_client()

        # Build callback URL
        origin = request.headers.get("origin", "http://localhost:8200")
        callback_url = f"{origin}/api/auth/callback"

        if data.redirect:
            callback_url += f"?next={data.redirect}"

        # Send magic link
        response = client.auth.sign_in_with_otp(
            {
                "email": data.email,
                "options": {
                    "email_redirect_to": callback_url,
                }
            }
        )

        return MagicLinkResponse(
            success=True,
            message="Check your email for the magic link!"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send magic link: {str(e)}"
        )


@router.get("/callback")
async def auth_callback(request: Request, code: Optional[str] = None, next: Optional[str] = None):
    """
    Handle the OAuth/magic link callback from Supabase.

    Exchanges the code for a session and sets authentication cookies.
    """
    if not config.supabase.is_configured:
        return RedirectResponse(url="/login?error=auth_not_configured")

    if not code:
        return RedirectResponse(url="/login?error=missing_code")

    try:
        client = get_supabase_client()

        # Exchange code for session
        response = client.auth.exchange_code_for_session({"auth_code": code})

        if response.session:
            # Create redirect response
            redirect_url = next or "/"
            redirect_response = RedirectResponse(
                url=redirect_url,
                status_code=status.HTTP_302_FOUND
            )

            # Set authentication cookies
            access_token = response.session.access_token
            refresh_token = response.session.refresh_token

            # Set cookies (httponly for security)
            redirect_response.set_cookie(
                key="sb-access-token",
                value=access_token,
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 7,  # 7 days
            )

            if refresh_token:
                redirect_response.set_cookie(
                    key="sb-refresh-token",
                    value=refresh_token,
                    httponly=True,
                    secure=True,
                    samesite="lax",
                    max_age=60 * 60 * 24 * 30,  # 30 days
                )

            return redirect_response

        return RedirectResponse(url="/login?error=session_error")

    except Exception as e:
        return RedirectResponse(url=f"/login?error={str(e)}")


@router.post("/logout")
async def logout(request: Request):
    """
    Log out the current user by clearing session cookies.
    """
    response = JSONResponse(content={"success": True, "message": "Logged out"})

    # Clear authentication cookies
    response.delete_cookie("sb-access-token")
    response.delete_cookie("sb-refresh-token")
    response.delete_cookie("access_token")

    return response


@router.get("/logout")
async def logout_redirect(request: Request):
    """
    Log out and redirect to home page.
    """
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    # Clear authentication cookies
    response.delete_cookie("sb-access-token")
    response.delete_cookie("sb-refresh-token")
    response.delete_cookie("access_token")

    return response


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """
    Get the current authenticated user's information.
    """
    # Try to get profile from Supabase
    profile = None
    try:
        profile = await get_user_profile(user.id)
    except Exception:
        pass

    return UserResponse(
        id=user.id,
        email=user.email,
        membership_tier=user.membership_tier,
        profile=profile
    )


@router.get("/status")
async def auth_status(user: Optional[User] = Depends(get_optional_user)):
    """
    Check authentication status without requiring authentication.

    Useful for frontend to check if user is logged in.
    """
    if user:
        return {
            "authenticated": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "membership_tier": user.membership_tier,
            }
        }

    return {"authenticated": False, "user": None}


@router.post("/refresh")
async def refresh_token(request: Request):
    """
    Refresh the access token using the refresh token.
    """
    if not config.supabase.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured"
        )

    refresh_token = request.cookies.get("sb-refresh-token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token found"
        )

    try:
        client = get_supabase_client()
        response = client.auth.refresh_session(refresh_token)

        if response.session:
            json_response = JSONResponse(
                content={"success": True, "message": "Token refreshed"}
            )

            # Update cookies
            json_response.set_cookie(
                key="sb-access-token",
                value=response.session.access_token,
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 7,
            )

            if response.session.refresh_token:
                json_response.set_cookie(
                    key="sb-refresh-token",
                    value=response.session.refresh_token,
                    httponly=True,
                    secure=True,
                    samesite="lax",
                    max_age=60 * 60 * 24 * 30,
                )

            return json_response

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to refresh token"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token refresh failed: {str(e)}"
        )
