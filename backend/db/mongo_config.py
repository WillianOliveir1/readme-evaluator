"""MongoDB Atlas configuration and utilities.

This module handles connection to MongoDB Atlas with proper error handling,
connection pooling, and configuration validation.

Environment variables expected:
  - MONGODB_URI: MongoDB connection string (e.g., mongodb+srv://user:pass@cluster.mongodb.net)
  - MONGODB_DB: Database name (default: "readme_evaluator")
  - MONGODB_COLLECTION: Collection name (default: "evaluations")
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

LOG = logging.getLogger(__name__)


class MongoDBConfig:
    """MongoDB configuration and connection management."""

    def __init__(
        self,
        uri: Optional[str] = None,
        db_name: Optional[str] = None,
        collection_name: Optional[str] = None,
        timeout_seconds: int = 30,
    ):
        """Initialize MongoDB configuration.

        Args:
            uri: MongoDB connection string. If None, reads from MONGODB_URI env var.
            db_name: Database name. If None, defaults to 'readme-evaluator'.
            collection_name: Collection name. If None, defaults to 'evaluations'.
            timeout_seconds: Connection timeout in seconds.
        """
        self.uri = uri or os.getenv("MONGODB_URI")
        self.db_name = db_name or os.getenv("MONGODB_DB", "readme-evaluator")
        self.collection_name = collection_name or os.getenv("MONGODB_COLLECTION", "evaluations")
        self.timeout_seconds = timeout_seconds
        self._client: Optional[MongoClient] = None
        self._is_connected = False

    def validate(self) -> bool:
        """Validate MongoDB connection configuration.

        Returns:
            True if connection successful, False otherwise.
        """
        if not self.uri:
            LOG.warning("MONGODB_URI not configured. MongoDB persistence disabled.")
            return False

        try:
            # Create a temporary client with short timeout for validation
            test_client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=self.timeout_seconds * 1000,
                connectTimeoutMS=self.timeout_seconds * 1000,
            )
            # Force connection test
            test_client.admin.command("ping")
            test_client.close()
            LOG.info("MongoDB connection validated successfully")
            self._is_connected = True
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            LOG.error(f"MongoDB connection failed: {e}")
            self._is_connected = False
            return False
        except Exception as e:
            LOG.error(f"Unexpected error validating MongoDB connection: {e}")
            self._is_connected = False
            return False

    def get_client(self) -> Optional[MongoClient]:
        """Get or create MongoDB client with connection pooling.

        Returns:
            MongoClient instance or None if not configured.
        """
        if not self.uri:
            return None

        if self._client is None:
            try:
                self._client = MongoClient(
                    self.uri,
                    serverSelectionTimeoutMS=self.timeout_seconds * 1000,
                    retryWrites=True,
                    maxPoolSize=10,
                    minPoolSize=1,
                )
                LOG.info("MongoDB client created with connection pooling")
            except Exception as e:
                LOG.error(f"Failed to create MongoDB client: {e}")
                return None

        return self._client

    def get_collection(self):
        """Get MongoDB collection.

        Returns:
            MongoDB collection or None if not configured/connected.
        """
        client = self.get_client()
        if not client:
            return None

        try:
            db = client[self.db_name]
            collection = db[self.collection_name]
            return collection
        except Exception as e:
            LOG.error(f"Failed to get collection: {e}")
            return None

    def close(self):
        """Close MongoDB connection."""
        if self._client:
            try:
                self._client.close()
                self._client = None
                self._is_connected = False
                LOG.info("MongoDB connection closed")
            except Exception as e:
                LOG.error(f"Error closing MongoDB connection: {e}")

    @staticmethod
    def from_env() -> MongoDBConfig:
        """Create configuration from environment variables.

        Returns:
            MongoDBConfig instance.
        """
        return MongoDBConfig(
            uri=os.getenv("MONGODB_URI"),
            db_name=os.getenv("MONGODB_DB", "readme-evaluator"),
            collection_name=os.getenv("MONGODB_COLLECTION", "evaluations"),
        )


# Global instance (lazy initialized)
_global_config: Optional[MongoDBConfig] = None


def get_mongodb_config() -> MongoDBConfig:
    """Get or create global MongoDB configuration.

    Returns:
        MongoDBConfig instance.
    """
    global _global_config
    if _global_config is None:
        _global_config = MongoDBConfig.from_env()
    return _global_config


def close_mongodb():
    """Close global MongoDB connection."""
    global _global_config
    if _global_config:
        _global_config.close()
