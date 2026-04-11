"""
Daily.co API integration utilities.

Handles:
- Room creation
- Meeting token generation
- Room management
"""

import httpx
from typing import Optional, Dict, Any
from app.config import get_settings

settings = get_settings()


class DailyCoError(Exception):
    """Custom exception for Daily.co API errors."""
    pass


async def create_room(
    name: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a Daily.co room.

    Args:
        name: Optional custom room name (will be auto-generated if not provided)
        properties: Room configuration properties

    Returns:
        Room data including room name and URL

    Raises:
        DailyCoError: If room creation fails
    """
    if not settings.DAILY_API_KEY:
        raise DailyCoError("DAILY_API_KEY not configured")

    url = f"{settings.DAILY_API_URL}/rooms"
    headers = {
        "Authorization": f"Bearer {settings.DAILY_API_KEY}",
        "Content-Type": "application/json",
    }

    # Default room properties
    default_properties = {
        "enable_screenshare": True,
        "enable_chat": False,  # We'll use our own chat/transcript UI
        "enable_knocking": False,  # Direct join
        "enable_recording": "cloud",  # For future transcript storage
        "max_participants": 20,  # Per SRS NFR-005
        "autojoin": True,
    }

    if properties:
        default_properties.update(properties)

    payload = {"properties": default_properties}
    if name:
        payload["name"] = name

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text
            raise DailyCoError(f"Failed to create Daily.co room: {error_detail}")
        except httpx.RequestError as e:
            raise DailyCoError(f"Daily.co API request failed: {str(e)}")


async def create_meeting_token(
    room_name: str,
    user_name: Optional[str] = None,
    user_id: Optional[str] = None,
    is_owner: bool = False,
    enable_recording: bool = False,
) -> str:
    """
    Generate a meeting token for a participant.

    Args:
        room_name: Daily.co room name
        user_name: Display name for the participant
        user_id: Unique identifier for the participant
        is_owner: Whether the participant has owner privileges
        enable_recording: Whether this participant can record

    Returns:
        Meeting token string

    Raises:
        DailyCoError: If token generation fails
    """
    if not settings.DAILY_API_KEY:
        raise DailyCoError("DAILY_API_KEY not configured")

    url = f"{settings.DAILY_API_URL}/meeting-tokens"
    headers = {
        "Authorization": f"Bearer {settings.DAILY_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "properties": {
            "room_name": room_name,
        }
    }

    if user_name:
        payload["properties"]["user_name"] = user_name

    if user_id:
        payload["properties"]["user_id"] = user_id

    if is_owner:
        payload["properties"]["is_owner"] = True

    if enable_recording:
        payload["properties"]["enable_recording"] = "cloud"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            return data["token"]
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text
            raise DailyCoError(f"Failed to create meeting token: {error_detail}")
        except httpx.RequestError as e:
            raise DailyCoError(f"Daily.co API request failed: {str(e)}")


async def delete_room(room_name: str) -> None:
    """
    Delete a Daily.co room.

    Args:
        room_name: Name of the room to delete

    Raises:
        DailyCoError: If deletion fails
    """
    if not settings.DAILY_API_KEY:
        raise DailyCoError("DAILY_API_KEY not configured")

    url = f"{settings.DAILY_API_URL}/rooms/{room_name}"
    headers = {
        "Authorization": f"Bearer {settings.DAILY_API_KEY}",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(url, headers=headers, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # 404 is OK - room doesn't exist
            if e.response.status_code != 404:
                error_detail = e.response.text
                raise DailyCoError(f"Failed to delete Daily.co room: {error_detail}")
        except httpx.RequestError as e:
            raise DailyCoError(f"Daily.co API request failed: {str(e)}")


async def get_room(room_name: str) -> Optional[Dict[str, Any]]:
    """
    Get room information.

    Args:
        room_name: Name of the room

    Returns:
        Room data or None if room doesn't exist

    Raises:
        DailyCoError: If request fails
    """
    if not settings.DAILY_API_KEY:
        raise DailyCoError("DAILY_API_KEY not configured")

    url = f"{settings.DAILY_API_URL}/rooms/{room_name}"
    headers = {
        "Authorization": f"Bearer {settings.DAILY_API_KEY}",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            error_detail = e.response.text
            raise DailyCoError(f"Failed to get Daily.co room: {error_detail}")
        except httpx.RequestError as e:
            raise DailyCoError(f"Daily.co API request failed: {str(e)}")
