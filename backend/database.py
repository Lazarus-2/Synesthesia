from motor.motor_asyncio import AsyncIOMotorClient
from backend.config import get_settings

settings = get_settings()

# Lazy initialization
_client = None
_db = None

def get_mongodb_client() -> AsyncIOMotorClient:
    """Lazy-load the MongoDB client."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client

def get_mongodb():
    """FastAPI Dependency generator yielding the async MongoDB instance."""
    global _db
    if _db is None:
        _db = get_mongodb_client()[settings.mongo_db_name]
    return _db

async def init_mongodb():
    """Initializes indexes on collections for optimized performance."""
    db = get_mongodb()
    await db.users.create_index("username")
    await db.chat_sessions.create_index("user_id")

# --- Legacy Compatibility Stubs ---
def create_db_and_tables():
    """Stub to support legacy startup sequences."""
    pass

def get_session():
    """Stub to prevent SQL dependency generation issues."""
    yield None

class DummyEngine:
    pass

engine = DummyEngine()
