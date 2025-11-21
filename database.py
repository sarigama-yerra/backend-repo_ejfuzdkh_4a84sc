import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient
from pymongo.collection import Collection

DATABASE_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "app_db")

client: Optional[MongoClient] = None
_db = None

try:
    client = MongoClient(DATABASE_URL)
    _db = client[DATABASE_NAME]
except Exception as e:
    client = None
    _db = None

db = _db


def _collection(name: str) -> Collection:
    if db is None:
        raise RuntimeError("Database is not initialized")
    return db[name]


def create_document(collection_name: str, data: Dict[str, Any]) -> str:
    col = _collection(collection_name)
    now = datetime.utcnow()
    data["created_at"] = now
    data["updated_at"] = now
    result = col.insert_one(data)
    return str(result.inserted_id)


def get_documents(collection_name: str, filter_dict: Dict[str, Any] | None = None, limit: int = 100, sort: Optional[list] = None) -> List[Dict[str, Any]]:
    col = _collection(collection_name)
    cursor = col.find(filter_dict or {})
    if sort:
        cursor = cursor.sort(sort)
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


def update_document(collection_name: str, filter_dict: Dict[str, Any], update_dict: Dict[str, Any]) -> int:
    col = _collection(collection_name)
    update_dict["updated_at"] = datetime.utcnow()
    result = col.update_one(filter_dict, {"$set": update_dict})
    return result.modified_count


def delete_document(collection_name: str, filter_dict: Dict[str, Any]) -> int:
    col = _collection(collection_name)
    result = col.delete_one(filter_dict)
    return result.deleted_count
