import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID", 898508164))
    DATABASE_URL = os.getenv("DATABASE_URL")
    
config = Config()
