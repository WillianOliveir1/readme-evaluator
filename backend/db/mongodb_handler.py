"""MongoDB Handler Class for Read and Write Operations.

This module provides a convenient MongoDB handler class that simplifies
read and write operations with proper error handling and connection management.

Example usage:
    from backend.db.mongodb_handler import MongoDBHandler
    
    handler = MongoDBHandler()
    
    # Write
    result = handler.insert_one({"name": "test", "value": 123})
    
    # Read
    docs = handler.find_all()
    doc = handler.find_one({"name": "test"})
    
    # Update
    updated = handler.update_one({"name": "test"}, {"$set": {"value": 456}})
    
    # Delete
    deleted = handler.delete_one({"name": "test"})
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

from pymongo import MongoClient
from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError,
    OperationFailure,
    DuplicateKeyError,
)
from pymongo.collection import Collection
from bson.objectid import ObjectId

from backend.config import MONGODB_URI, MONGODB_DB_NAME, MONGODB_COLLECTION_NAME

LOG = logging.getLogger(__name__)


class MongoDBHandler:
    """Handler for MongoDB read and write operations."""

    def __init__(
        self,
        uri: Optional[str] = None,
        db_name: Optional[str] = None,
        collection_name: Optional[str] = None,
        timeout_seconds: int = 30,
        auto_connect: bool = True,
    ):
        """Initialize MongoDB Handler.

        Args:
            uri: MongoDB connection string. Reads from MONGODB_URI env var if None.
            db_name: Database name. Defaults to 'readme-evaluator'.
            collection_name: Collection name. Defaults to 'evaluations'.
            timeout_seconds: Connection timeout in seconds.
            auto_connect: Whether to connect automatically on initialization.

        Raises:
            ValueError: If MongoDB URI is not provided and MONGODB_URI env var is not set.
        """
        self.uri = uri or MONGODB_URI
        self.db_name = db_name or MONGODB_DB_NAME
        self.collection_name = collection_name or MONGODB_COLLECTION_NAME
        self.timeout_seconds = timeout_seconds

        self._client: Optional[MongoClient] = None
        self._collection: Optional[Collection] = None
        self._is_connected = False

        if not self.uri:
            raise ValueError(
                "MongoDB URI must be provided or set in MONGODB_URI environment variable"
            )

        if auto_connect:
            self.connect()

    def connect(self) -> bool:
        """Connect to MongoDB.

        Returns:
            bool: True if connection successful, False otherwise.
        """
        try:
            self._client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=self.timeout_seconds * 1000,
                connectTimeoutMS=self.timeout_seconds * 1000,
                retryWrites=True,
                maxPoolSize=10,
                minPoolSize=1,
            )
            # Test connection
            self._client.admin.command("ping")
            self._collection = self._client[self.db_name][self.collection_name]
            self._is_connected = True
            LOG.info(
                f"Connected to MongoDB: {self.db_name}.{self.collection_name}"
            )
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            LOG.error(f"MongoDB connection failed: {e}")
            self._is_connected = False
            return False
        except Exception as e:
            LOG.error(f"Unexpected error connecting to MongoDB: {e}")
            self._is_connected = False
            return False

    def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            try:
                self._client.close()
                self._client = None
                self._collection = None
                self._is_connected = False
                LOG.info("Disconnected from MongoDB")
            except Exception as e:
                LOG.error(f"Error closing MongoDB connection: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if handler is connected to MongoDB.

        Returns:
            bool: True if connected, False otherwise.
        """
        return self._is_connected

    @property
    def collection(self) -> Optional[Collection]:
        """Get the MongoDB collection.

        Returns:
            Collection or None if not connected.
        """
        return self._collection

    def _ensure_connected(self) -> bool:
        """Ensure handler is connected to MongoDB.

        Returns:
            bool: True if connected, False otherwise.
        """
        if not self._is_connected:
            LOG.warning("Handler not connected. Attempting to reconnect...")
            return self.connect()
        return True

    def _get_collection(self) -> Collection:
        """Return the active collection, raising if unavailable."""
        if self._collection is None:
            raise RuntimeError("MongoDB collection is not initialised")
        return self._collection

    # ==================== INSERT OPERATIONS ====================

    def insert_one(
        self, document: Dict[str, Any], add_timestamp: bool = True
    ) -> Optional[str]:
        """Insert a single document into the collection.

        Args:
            document: Dictionary to insert.
            add_timestamp: Whether to add _inserted_at timestamp.

        Returns:
            str: Inserted document ID, or None on failure.
        """
        if not self._ensure_connected():
            LOG.error("Cannot insert: not connected to MongoDB")
            return None

        try:
            doc = dict(document)
            if add_timestamp:
                doc["_inserted_at"] = datetime.utcnow().isoformat()

            result = self._get_collection().insert_one(doc)
            inserted_id = str(result.inserted_id)
            LOG.info(f"Document inserted: {inserted_id}")
            return inserted_id
        except DuplicateKeyError as e:
            LOG.error(f"Duplicate key error: {e}")
            return None
        except Exception as e:
            LOG.error(f"Failed to insert document: {e}")
            return None

    def insert_many(
        self, documents: List[Dict[str, Any]], add_timestamp: bool = True
    ) -> Optional[List[str]]:
        """Insert multiple documents into the collection.

        Args:
            documents: List of dictionaries to insert.
            add_timestamp: Whether to add _inserted_at timestamp to each.

        Returns:
            List of inserted document IDs, or None on failure.
        """
        if not self._ensure_connected():
            LOG.error("Cannot insert: not connected to MongoDB")
            return None

        try:
            docs = []
            for doc in documents:
                d = dict(doc)
                if add_timestamp:
                    d["_inserted_at"] = datetime.utcnow().isoformat()
                docs.append(d)

            result = self._get_collection().insert_many(docs)
            inserted_ids = [str(id_) for id_ in result.inserted_ids]
            LOG.info(f"Inserted {len(inserted_ids)} documents")
            return inserted_ids
        except Exception as e:
            LOG.error(f"Failed to insert documents: {e}")
            return None

    # ==================== READ OPERATIONS ====================

    def find_one(
        self, query: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, int]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find a single document.

        Args:
            query: MongoDB query filter. Defaults to empty (first document).
            projection: Fields to include/exclude (1 for include, 0 for exclude).

        Returns:
            Document as dictionary, or None if not found.
        """
        if not self._ensure_connected():
            LOG.error("Cannot query: not connected to MongoDB")
            return None

        try:
            query = query or {}
            result = self._get_collection().find_one(query, projection)
            if result:
                # Convert ObjectId to string for JSON serialization
                result["_id"] = str(result["_id"])
            return result
        except Exception as e:
            LOG.error(f"Failed to find document: {e}")
            return None

    def find_all(
        self, query: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, int]] = None
    ) -> List[Dict[str, Any]]:
        """Find all documents matching the query.

        Args:
            query: MongoDB query filter. Defaults to empty (all documents).
            projection: Fields to include/exclude.

        Returns:
            List of documents as dictionaries.
        """
        if not self._ensure_connected():
            LOG.error("Cannot query: not connected to MongoDB")
            return []

        try:
            query = query or {}
            cursor = self._get_collection().find(query, projection)
            documents = []
            for doc in cursor:
                doc["_id"] = str(doc["_id"])
                documents.append(doc)
            LOG.info(f"Found {len(documents)} documents")
            return documents
        except Exception as e:
            LOG.error(f"Failed to find documents: {e}")
            return []

    def find_by_id(
        self, document_id: str, projection: Optional[Dict[str, int]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find a document by its ObjectId.

        Args:
            document_id: The document's ObjectId as string.
            projection: Fields to include/exclude.

        Returns:
            Document as dictionary, or None if not found.
        """
        if not self._ensure_connected():
            LOG.error("Cannot query: not connected to MongoDB")
            return None

        try:
            object_id = ObjectId(document_id)
            return self.find_one({"_id": object_id}, projection)
        except Exception as e:
            LOG.error(f"Failed to find document by ID: {e}")
            return None

    def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        """Count documents matching the query.

        Args:
            query: MongoDB query filter. Defaults to all documents.

        Returns:
            Number of matching documents.
        """
        if not self._ensure_connected():
            LOG.error("Cannot query: not connected to MongoDB")
            return 0

        try:
            query = query or {}
            count = self._get_collection().count_documents(query)
            return count
        except Exception as e:
            LOG.error(f"Failed to count documents: {e}")
            return 0

    # ==================== UPDATE OPERATIONS ====================

    def update_one(
        self, query: Dict[str, Any], update: Dict[str, Any]
    ) -> Optional[int]:
        """Update a single document.

        Args:
            query: MongoDB query to find the document.
            update: Update operations (e.g., {"$set": {"field": "value"}}).

        Returns:
            Number of documents modified, or None on failure.
        """
        if not self._ensure_connected():
            LOG.error("Cannot update: not connected to MongoDB")
            return None

        try:
            # Add updated_at timestamp
            update_with_timestamp = dict(update)
            if "$set" not in update_with_timestamp:
                update_with_timestamp["$set"] = {}
            update_with_timestamp["$set"]["_updated_at"] = datetime.utcnow().isoformat()

            result = self._get_collection().update_one(query, update_with_timestamp)
            LOG.info(f"Modified {result.modified_count} document(s)")
            return result.modified_count
        except Exception as e:
            LOG.error(f"Failed to update document: {e}")
            return None

    def update_many(
        self, query: Dict[str, Any], update: Dict[str, Any]
    ) -> Optional[int]:
        """Update multiple documents.

        Args:
            query: MongoDB query to find documents.
            update: Update operations.

        Returns:
            Number of documents modified, or None on failure.
        """
        if not self._ensure_connected():
            LOG.error("Cannot update: not connected to MongoDB")
            return None

        try:
            # Add updated_at timestamp
            update_with_timestamp = dict(update)
            if "$set" not in update_with_timestamp:
                update_with_timestamp["$set"] = {}
            update_with_timestamp["$set"]["_updated_at"] = datetime.utcnow().isoformat()

            result = self._get_collection().update_many(query, update_with_timestamp)
            LOG.info(f"Modified {result.modified_count} document(s)")
            return result.modified_count
        except Exception as e:
            LOG.error(f"Failed to update documents: {e}")
            return None

    def replace_one(
        self, query: Dict[str, Any], replacement: Dict[str, Any]
    ) -> Optional[int]:
        """Replace a single document.

        Args:
            query: MongoDB query to find the document.
            replacement: New document content.

        Returns:
            Number of documents replaced (0 or 1), or None on failure.
        """
        if not self._ensure_connected():
            LOG.error("Cannot replace: not connected to MongoDB")
            return None

        try:
            replacement_with_timestamp = dict(replacement)
            replacement_with_timestamp["_replaced_at"] = datetime.utcnow().isoformat()

            result = self._get_collection().replace_one(query, replacement_with_timestamp)
            LOG.info(f"Replaced {result.modified_count} document(s)")
            return result.modified_count
        except Exception as e:
            LOG.error(f"Failed to replace document: {e}")
            return None

    # ==================== DELETE OPERATIONS ====================

    def delete_one(self, query: Dict[str, Any]) -> Optional[int]:
        """Delete a single document.

        Args:
            query: MongoDB query to find the document.

        Returns:
            Number of documents deleted (0 or 1), or None on failure.
        """
        if not self._ensure_connected():
            LOG.error("Cannot delete: not connected to MongoDB")
            return None

        try:
            result = self._get_collection().delete_one(query)
            LOG.info(f"Deleted {result.deleted_count} document(s)")
            return result.deleted_count
        except Exception as e:
            LOG.error(f"Failed to delete document: {e}")
            return None

    def delete_many(self, query: Dict[str, Any]) -> Optional[int]:
        """Delete multiple documents.

        Args:
            query: MongoDB query to find documents.

        Returns:
            Number of documents deleted, or None on failure.
        """
        if not self._ensure_connected():
            LOG.error("Cannot delete: not connected to MongoDB")
            return None

        try:
            result = self._get_collection().delete_many(query)
            LOG.info(f"Deleted {result.deleted_count} document(s)")
            return result.deleted_count
        except Exception as e:
            LOG.error(f"Failed to delete documents: {e}")
            return None

    def delete_all(self) -> Optional[int]:
        """Delete all documents in the collection. Use with caution!

        Returns:
            Number of documents deleted, or None on failure.
        """
        if not self._ensure_connected():
            LOG.error("Cannot delete: not connected to MongoDB")
            return None

        try:
            result = self._get_collection().delete_many({})
            LOG.warning(f"Deleted {result.deleted_count} document(s)")
            return result.deleted_count
        except Exception as e:
            LOG.error(f"Failed to delete all documents: {e}")
            return None

    # ==================== BULK OPERATIONS ====================

    def bulk_write(self, operations: List[Any]) -> Optional[Dict[str, Any]]:
        """Execute bulk write operations.

        Args:
            operations: List of pymongo bulk write operations.

        Returns:
            Result summary as dictionary, or None on failure.

        Example:
            from pymongo import UpdateOne, InsertOne
            
            operations = [
                InsertOne({"name": "Alice"}),
                UpdateOne({"name": "Bob"}, {"$set": {"age": 30}}),
            ]
            result = handler.bulk_write(operations)
        """
        if not self._ensure_connected():
            LOG.error("Cannot bulk write: not connected to MongoDB")
            return None

        try:
            result = self._get_collection().bulk_write(operations)
            LOG.info(f"Bulk write completed: {result.acknowledged}")
            return {
                "acknowledged": result.acknowledged,
                "inserted_count": result.inserted_count,
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
                "deleted_count": result.deleted_count,
            }
        except Exception as e:
            LOG.error(f"Failed to execute bulk write: {e}")
            return None

    # ==================== CONTEXT MANAGER ====================

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def __del__(self):
        """Destructor to ensure connection is closed."""
        self.disconnect()


# Convenience functions for quick operations

def get_handler(
    uri: Optional[str] = None,
    db_name: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> Optional[MongoDBHandler]:
    """Create a MongoDB handler instance.

    Args:
        uri: MongoDB URI (reads from MONGODB_URI env var if not provided).
        db_name: Database name.
        collection_name: Collection name.

    Returns:
        MongoDBHandler instance or None if connection fails.
    """
    try:
        return MongoDBHandler(uri, db_name, collection_name)
    except ValueError as e:
        LOG.error(f"Failed to create MongoDB handler: {e}")
        return None
