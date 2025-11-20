"""Test script for MongoDB Handler - Demonstra leitura e escrita no MongoDB.

Execute este script para testar a conexão e operações básicas com MongoDB:
    python test_mongodb_handler.py
"""
import logging
import os
from pathlib import Path
from datetime import datetime

# Load environment variables from .env
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from backend.db.mongodb_handler import MongoDBHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)


def test_connection():
    """Test MongoDB connection."""
    LOG.info("=" * 60)
    LOG.info("TEST 1: Connection Test")
    LOG.info("=" * 60)
    
    try:
        handler = MongoDBHandler()
        LOG.info(f"✓ Connected successfully!")
        LOG.info(f"  Database: {handler.db_name}")
        LOG.info(f"  Collection: {handler.collection_name}")
        LOG.info(f"  Is Connected: {handler.is_connected}")
        handler.disconnect()
        return True
    except ValueError as e:
        LOG.error(f"✗ Connection failed: {e}")
        return False


def test_insert_operations():
    """Test insert operations."""
    LOG.info("\n" + "=" * 60)
    LOG.info("TEST 2: Insert Operations")
    LOG.info("=" * 60)
    
    try:
        handler = MongoDBHandler()
        
        # Insert single document
        LOG.info("\n2.1 - Inserting single document...")
        doc1 = {
            "title": "Python MongoDB Guide",
            "author": "John Doe",
            "tags": ["python", "mongodb", "database"],
            "views": 1000
        }
        id1 = handler.insert_one(doc1)
        LOG.info(f"✓ Document inserted with ID: {id1}")
        
        # Insert multiple documents
        LOG.info("\n2.2 - Inserting multiple documents...")
        docs = [
            {
                "title": "FastAPI Tutorial",
                "author": "Jane Smith",
                "tags": ["fastapi", "api", "python"],
                "views": 2500
            },
            {
                "title": "MongoDB Best Practices",
                "author": "Bob Johnson",
                "tags": ["mongodb", "performance", "data"],
                "views": 1800
            }
        ]
        ids = handler.insert_many(docs)
        LOG.info(f"✓ {len(ids)} documents inserted with IDs: {ids}")
        
        handler.disconnect()
        return True, id1, ids
    except Exception as e:
        LOG.error(f"✗ Insert operation failed: {e}")
        return False, None, None


def test_read_operations(id1, ids):
    """Test read operations."""
    LOG.info("\n" + "=" * 60)
    LOG.info("TEST 3: Read Operations")
    LOG.info("=" * 60)
    
    try:
        handler = MongoDBHandler()
        
        # Find all documents
        LOG.info("\n3.1 - Finding all documents...")
        all_docs = handler.find_all()
        LOG.info(f"✓ Found {len(all_docs)} documents total")
        for doc in all_docs[:3]:  # Show first 3
            LOG.info(f"  - {doc.get('title', 'N/A')} by {doc.get('author', 'N/A')}")
        
        # Find one document
        LOG.info("\n3.2 - Finding one document...")
        doc = handler.find_one({"author": "John Doe"})
        if doc:
            LOG.info(f"✓ Found: {doc['title']} - {doc['views']} views")
        
        # Find by ID
        LOG.info("\n3.3 - Finding document by ID...")
        doc_by_id = handler.find_by_id(id1)
        if doc_by_id:
            LOG.info(f"✓ Found by ID: {doc_by_id['title']}")
        
        # Count documents
        LOG.info("\n3.4 - Counting documents...")
        count = handler.count_documents()
        LOG.info(f"✓ Total documents in collection: {count}")
        
        # Count with filter
        python_count = handler.count_documents({"tags": "python"})
        LOG.info(f"✓ Documents with 'python' tag: {python_count}")
        
        handler.disconnect()
        return True
    except Exception as e:
        LOG.error(f"✗ Read operation failed: {e}")
        return False


def test_update_operations(id1):
    """Test update operations."""
    LOG.info("\n" + "=" * 60)
    LOG.info("TEST 4: Update Operations")
    LOG.info("=" * 60)
    
    try:
        handler = MongoDBHandler()
        
        # Update one document
        LOG.info("\n4.1 - Updating single document...")
        modified = handler.update_one(
            {"_id": id1},
            {"$set": {"views": 5000, "updated_by": "test_script"}}
        )
        LOG.info(f"✓ Updated {modified} document(s)")
        
        # Verify update
        updated_doc = handler.find_by_id(id1)
        LOG.info(f"  New views count: {updated_doc['views']}")
        
        # Update many documents
        LOG.info("\n4.2 - Updating multiple documents...")
        modified = handler.update_many(
            {"tags": "python"},
            {"$set": {"category": "programming"}}
        )
        LOG.info(f"✓ Updated {modified} document(s) with 'python' tag")
        
        handler.disconnect()
        return True
    except Exception as e:
        LOG.error(f"✗ Update operation failed: {e}")
        return False


def test_delete_operations():
    """Test delete operations."""
    LOG.info("\n" + "=" * 60)
    LOG.info("TEST 5: Delete Operations")
    LOG.info("=" * 60)
    
    try:
        handler = MongoDBHandler()
        
        # Find document to delete
        LOG.info("\n5.1 - Finding document to delete...")
        doc_to_delete = handler.find_one({"author": "Bob Johnson"})
        if doc_to_delete:
            doc_id = doc_to_delete["_id"]
            LOG.info(f"  Found: {doc_to_delete['title']}")
            
            # Delete one document
            LOG.info("\n5.2 - Deleting document...")
            deleted = handler.delete_one({"_id": doc_id})
            LOG.info(f"✓ Deleted {deleted} document(s)")
        
        handler.disconnect()
        return True
    except Exception as e:
        LOG.error(f"✗ Delete operation failed: {e}")
        return False


def test_context_manager():
    """Test using handler as context manager."""
    LOG.info("\n" + "=" * 60)
    LOG.info("TEST 6: Context Manager Usage")
    LOG.info("=" * 60)
    
    try:
        LOG.info("\n6.1 - Using handler with 'with' statement...")
        with MongoDBHandler() as handler:
            count = handler.count_documents()
            LOG.info(f"✓ Found {count} documents in collection")
            LOG.info(f"  Connected: {handler.is_connected}")
        
        LOG.info("\n6.2 - After context manager exit...")
        LOG.info("✓ Handler automatically disconnected")
        return True
    except Exception as e:
        LOG.error(f"✗ Context manager test failed: {e}")
        return False


def main():
    """Run all tests."""
    LOG.info("\n")
    LOG.info("#" * 60)
    LOG.info("# MongoDB Handler Test Suite")
    LOG.info("#" * 60)
    LOG.info("# Using database: readme-evaluator")
    LOG.info("#" * 60)
    
    # Check if MONGODB_URI is set
    if not os.getenv("MONGODB_URI"):
        LOG.error("✗ MONGODB_URI environment variable not set!")
        LOG.info("  Please set it before running tests.")
        return
    
    results = []
    
    # Test 1: Connection
    result1 = test_connection()
    results.append(("Connection Test", result1))
    
    # Test 2: Insert operations
    result2, id1, ids = test_insert_operations()
    results.append(("Insert Operations", result2))
    
    if result2 and id1:
        # Test 3: Read operations
        result3 = test_read_operations(id1, ids)
        results.append(("Read Operations", result3))
        
        # Test 4: Update operations
        result4 = test_update_operations(id1)
        results.append(("Update Operations", result4))
        
        # Test 5: Delete operations
        # result5 = test_delete_operations()
        # results.append(("Delete Operations", result5))
    
    # Test 6: Context manager
    result6 = test_context_manager()
    results.append(("Context Manager", result6))
    
    # Summary
    LOG.info("\n" + "=" * 60)
    LOG.info("TEST SUMMARY")
    LOG.info("=" * 60)
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        LOG.info(f"{test_name}: {status}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    LOG.info(f"\nTotal: {passed}/{total} tests passed")
    LOG.info("=" * 60)


if __name__ == "__main__":
    main()
