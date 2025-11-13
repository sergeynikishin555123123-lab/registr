import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID", 898508164))
    
    # Manager group
    MANAGER_GROUP_ID = os.getenv("MANAGER_GROUP_ID")
    if MANAGER_GROUP_ID:
        MANAGER_GROUP_ID = int(MANAGER_GROUP_ID)
        print(f"✅ MANAGER_GROUP_ID настроен: {MANAGER_GROUP_ID}")
    else:
        MANAGER_GROUP_ID = None
        print("⚠️ MANAGER_GROUP_ID не настроен! Уведомления будут отправляться админу.")
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL").replace("postgresql://", "postgresql+asyncpg://")
    
    # Payments
    YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
    YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
    
    # Redis for scheduler
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Content files
    CONTENT_FILE = "content.csv"
    SCENARIOS_FILE = "scenarios.json"

config = Config()
