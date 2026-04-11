from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.utils.auth import decode_access_token
from app.database import get_database

security = HTTPBearer()


async def require_host(meeting: dict, current_user: dict) -> dict:
    """
    Raise HTTP 403 if ``current_user`` is not the host of ``meeting``.

    Returns the meeting dict on success so this can be used as a dependency
    or called directly in tests.
    """
    if str(meeting.get("host_id", "")) != str(current_user.get("id", "")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the meeting host can perform this action",
        )
    return meeting


async def require_participant(meeting: dict, current_user: dict) -> dict:
    """
    Raise HTTP 403 if ``current_user`` is not the host and not in invite_list.

    Email comparison is case-insensitive.
    Returns the meeting dict on success.
    """
    host_id = str(meeting.get("host_id", ""))
    if str(current_user.get("id", "")) == host_id:
        return meeting

    invite_list = [e.lower() for e in meeting.get("invite_list", [])]
    user_email = (current_user.get("email") or "").lower()

    if user_email and user_email in invite_list:
        return meeting

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You are not authorized to join this meeting",
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """FastAPI dependency — extracts and validates JWT, returns user dict."""
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    db = get_database()
    from bson import ObjectId

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return {
        "id": str(user["_id"]),
        "name": user["name"],
        "email": user["email"],
        "created_at": user["created_at"],
    }
