from app.core.mongo import mongo_db
from bson import ObjectId


class LessonRepository:
    def __init__(self):
        self.collection = mongo_db["lessons"]


lesson_repository = LessonRepository()
