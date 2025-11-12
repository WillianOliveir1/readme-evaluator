"""Simple persistence helpers.

This module provides two tiny helpers:
- save_to_mongo(document, uri, db_name, collection): attempts to insert to MongoDB
- save_to_file(document, path): fallback that writes JSON to a file (appends)

The project currently does not require an external DB; these helpers make it
easy to wire persistence later.
"""
from __future__ import annotations

import json
import datetime
from typing import Any, Dict, Optional


def save_to_file(document: Dict[str, Any], path: str) -> str:
    """Append a JSON document to `path` (creates file if missing). Returns path."""
    entry = {"_id": datetime.datetime.utcnow().isoformat(), "document": document}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def save_to_mongo(document: Dict[str, Any], uri: str, db_name: str, collection: str) -> Optional[str]:
    """Try to insert `document` into MongoDB. Returns inserted id as str or None on failure.

    Requires `pymongo` to be installed and a reachable MongoDB instance.
    """
    try:
        from pymongo import MongoClient
    except Exception:
        return None

    try:
        client = MongoClient(uri)
        db = client[db_name]
        coll = db[collection]
        res = coll.insert_one(document)
        return str(res.inserted_id)
    except Exception:
        return None
