from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as aioredis
from app.config import get_settings

settings = get_settings()

client: AsyncIOMotorClient = None
db = None
_redis_client = None


async def connect_to_mongo():
    """Connect to MongoDB on application startup."""
    global client, db
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]

    # Verify connection
    await client.admin.command("ping")
    print(f"Connected to MongoDB: {settings.MONGODB_DB_NAME}")


async def close_mongo_connection():
    """Close MongoDB connection on application shutdown."""
    global client, _redis_client
    if client:
        client.close()
        print("MongoDB connection closed")
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


def get_database():
    """Get the database instance."""
    return db


def get_redis():
    """Get (or lazily create) the Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
    return _redis_client
