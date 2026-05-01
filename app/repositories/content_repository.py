from app.core.mongo import mongo_db
from bson import ObjectId


class ContentRepository:
    def __init__(self):
        self.collection = mongo_db["lesson_contents"]


content_repository = ContentRepository()
