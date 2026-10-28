from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request, status

from app.config import get_settings


async def require_owner(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    if settings.owner_auth_mode == "disabled":
        if settings.app_env == "production" and not settings.auth_disabled_allowed:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Owner authentication is disabled in production; configuration is unsafe",
            )
        return
    if settings.owner_auth_mode != "token":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unsupported owner auth mode",
        )
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    cookie = request.cookies.get("discmon_owner")
    if not supplied and cookie:
        supplied = cookie
    if not supplied or not hmac.compare_digest(supplied, settings.owner_api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Owner authentication required",
        )
