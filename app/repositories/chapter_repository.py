from app.core.mongo import mongo_db
from bson import ObjectId


class ChapterRepository:
    def __init__(self):
        self.collection = mongo_db["chapters"]


chapter_repository = ChapterRepository()
