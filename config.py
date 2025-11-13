import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID", 898508164))
    MANAGER_GROUP_ID = int(os.getenv("MANAGER_GROUP_ID", -1003132221148))
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL").replace("postgresql://", "postgresql+asyncpg://")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Content
    CONTENT_FILE = "content.csv"

config = Config()
