from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
import httpx

from app.config import get_settings
from app.database import get_database
from app.deps import get_current_user
from app.models.user import (
    UserCreate,
    UserLogin,
    GoogleAuthRequest,
    UserResponse,
    AuthResponse,
)
from app.utils.auth import hash_password, verify_password, create_access_token

router = APIRouter()
settings = get_settings()


def _user_response(user: dict) -> UserResponse:
    """Convert a MongoDB user document to a UserResponse."""
    return UserResponse(
        id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        created_at=user["created_at"],
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate):
    """Register a new user with email and password."""
    db = get_database()

    # Check for existing user
    existing = await db.users.find_one({"email": data.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user document
    user_doc = {
        "name": data.name,
        "email": data.email,
        "password_hash": hash_password(data.password),
        "auth_provider": "email",
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id

    # Generate token
    token = create_access_token(str(result.inserted_id), data.email)

    return AuthResponse(
        access_token=token,
        user=_user_response(user_doc),
    )


@router.post("/login", response_model=AuthResponse)
async def login(data: UserLogin):
    """Login with email and password."""
    db = get_database()

    user = await db.users.find_one({"email": data.email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Users registered via Google won't have a password_hash
    if not user.get("password_hash"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account uses Google Sign-In. Please login with Google.",
        )

    if not verify_password(data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(str(user["_id"]), user["email"])

    return AuthResponse(
        access_token=token,
        user=_user_response(user),
    )


@router.post("/google", response_model=AuthResponse)
async def google_auth(data: GoogleAuthRequest):
    """Authenticate with a Google ID token."""
    # Verify the Google ID token
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={data.credential}"
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Google token",
                )
            google_user = resp.json()
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify Google token",
        )

    # Validate audience matches our client ID
    if google_user.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token audience mismatch",
        )

    email = google_user.get("email")
    name = google_user.get("name", email.split("@")[0])

    db = get_database()

    # Find or create user
    user = await db.users.find_one({"email": email})
    if not user:
        user_doc = {
            "name": name,
            "email": email,
            "password_hash": None,
            "auth_provider": "google",
            "google_id": google_user.get("sub"),
            "created_at": datetime.now(timezone.utc),
        }
        result = await db.users.insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        user = user_doc

    token = create_access_token(str(user["_id"]), user["email"])

    return AuthResponse(
        access_token=token,
        user=_user_response(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return UserResponse(**current_user)
