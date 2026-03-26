from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


class UserCreate(BaseModel):
    """Schema for user registration."""
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    """Schema for Google OAuth login."""
    credential: str


class UserResponse(BaseModel):
    """Schema for user data returned to the client."""
    id: str
    name: str
    email: str
    created_at: datetime


class AuthResponse(BaseModel):
    """Schema for auth responses containing a JWT token."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
