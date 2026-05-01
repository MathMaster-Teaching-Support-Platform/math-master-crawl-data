from app.core.mongo import mongo_db
from bson import ObjectId
from datetime import datetime, timezone


class BookRepository:
    def __init__(self):
        self.collection = mongo_db["books"]


book_repository = BookRepository()
