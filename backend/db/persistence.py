"""Persistence helpers for saving evaluation results.

This module provides:
- save_to_file(document, path): writes JSON to a file (appends)
- save_to_mongo(document, uri, db_name, collection): inserts to MongoDB
- save_with_mongo_fallback(document, file_path): saves to both MongoDB and file

Supports both direct connection and MongoDB Atlas with proper error handling.
"""
from __future__ import annotations

import json
import datetime
import logging
import os
from typing import Any, Dict, Optional, Tuple

from backend.config import MONGODB_URI, MONGODB_DB_NAME, MONGODB_COLLECTION_NAME

LOG = logging.getLogger(__name__)


def save_to_file(document: Dict[str, Any], path: str) -> str:
    """Append a JSON document to `path` (creates file if missing).

    Args:
        document: Dictionary to save
        path: File path to append to

    Returns:
        str: The file path
    """
    entry = {"_id": datetime.datetime.utcnow().isoformat(), "document": document}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def save_to_mongo(
    document: Dict[str, Any], uri: str, db_name: str, collection: str
) -> Optional[str]:
    """Insert a document into MongoDB. Returns inserted id as str or None on failure.

    Supports MongoDB Atlas connections and proper connection pooling.

    Args:
        document: Dictionary to insert
        uri: MongoDB connection string (supports mongodb+srv://)
        db_name: Database name
        collection: Collection name

    Returns:
        Optional[str]: Inserted document ID or None on failure
    """
    try:
        from pymongo import MongoClient
        from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
    except ImportError:
        LOG.warning("pymongo not installed. MongoDB persistence unavailable.")
        return None

    if not uri:
        LOG.warning("MongoDB URI not provided. Skipping MongoDB save.")
        return None

    try:
        client: MongoClient = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            retryWrites=True,
            maxPoolSize=10,
        )
        # Test connection
        client.admin.command("ping")

        db = client[db_name]
        coll = db[collection]

        # Add metadata
        doc_with_meta = {
            **document,
            "_saved_at": datetime.datetime.utcnow().isoformat(),
        }

        res = coll.insert_one(doc_with_meta)
        inserted_id = str(res.inserted_id)
        LOG.info(f"Document saved to MongoDB: {inserted_id}")
        client.close()
        return inserted_id

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        LOG.error(f"MongoDB connection failed: {e}")
        return None
    except Exception as e:
        LOG.error(f"Failed to save to MongoDB: {e}")
        return None


def save_with_mongo_fallback(
    document: Dict[str, Any], file_path: str, mongo_uri: Optional[str] = None,
    db_name: Optional[str] = None, collection: Optional[str] = None
) -> Tuple[Optional[str], str]:
    """Save document to MongoDB first, fallback to file if MongoDB fails.

    Args:
        document: Dictionary to save
        file_path: Fallback file path
        mongo_uri: MongoDB URI (reads from config if not provided)
        db_name: MongoDB database name (reads from config if not provided)
        collection: MongoDB collection name (reads from config if not provided)

    Returns:
        Tuple[Optional[str], str]: (mongo_id or None, file_path)
    """
    mongo_uri = mongo_uri or MONGODB_URI
    db_name = db_name or MONGODB_DB_NAME
    collection = collection or MONGODB_COLLECTION_NAME
    mongo_id = None

    # Try MongoDB first
    if mongo_uri:
        mongo_id = save_to_mongo(document, mongo_uri, db_name, collection)
        if mongo_id:
            LOG.info(f"Successfully saved to MongoDB: {mongo_id}")

    # Always save to file as well (for audit trail)
    file_result = save_to_file(document, file_path)
    LOG.info(f"Document also saved to file: {file_path}")

    return mongo_id, file_result
