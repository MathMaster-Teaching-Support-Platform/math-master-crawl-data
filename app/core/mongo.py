from motor.motor_asyncio import AsyncIOMotorClient
import os
 
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
mongo_client = AsyncIOMotorClient(MONGO_URL)
mongo_db = mongo_client[os.getenv("MONGO_DB", "sgk_toan")]