from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings

settings = get_settings()

client: AsyncIOMotorClient = None
db = None


async def connect_to_mongo():
    """Connect to MongoDB on application startup."""
    global client, db
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]

    # Verify connection
    await client.admin.command("ping")
    print(f"✅ Connected to MongoDB: {settings.MONGODB_DB_NAME}")


async def close_mongo_connection():
    """Close MongoDB connection on application shutdown."""
    global client
    if client:
        client.close()
        print("🔌 MongoDB connection closed")


def get_database():
    """Get the database instance."""
    return db
