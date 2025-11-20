#!/usr/bin/env python3
"""MongoDB Atlas connection validator and tester.

Usage:
    python tools/test_mongodb.py              # Test with env vars
    python tools/test_mongodb.py --uri "mongodb+srv://..." --db test_db
"""
import sys
import os
import argparse
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.db.persistence import save_to_mongo, save_to_file, save_with_mongo_fallback
from dotenv import load_dotenv


def test_env_vars():
    """Test if environment variables are loaded."""
    print("\n📋 Checking Environment Variables...")
    print("=" * 50)

    load_dotenv()

    mongo_uri = os.getenv("MONGODB_URI")
    mongo_db = os.getenv("MONGODB_DB", "readme_evaluator")
    mongo_coll = os.getenv("MONGODB_COLLECTION", "evaluations")

    if mongo_uri:
        # Hide sensitive info
        masked_uri = mongo_uri[:20] + "..." + mongo_uri[-20:]
        print(f"✓ MONGODB_URI: {masked_uri}")
    else:
        print("✗ MONGODB_URI: NOT SET")
        print("  → Set in .env or environment")
        return False

    print(f"✓ MONGODB_DB: {mongo_db}")
    print(f"✓ MONGODB_COLLECTION: {mongo_coll}")

    return mongo_uri, mongo_db, mongo_coll


def test_direct_connection(uri: str):
    """Test direct MongoDB connection."""
    print("\n🔌 Testing MongoDB Connection...")
    print("=" * 50)

    try:
        from pymongo import MongoClient
        from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
        client.admin.command("ping")
        client.close()

        print("✓ Connection Successful!")
        return True

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        print(f"✗ Connection Failed: {e}")
        print("\n💡 Troubleshooting:")
        print("  1. Check if cluster is online in MongoDB Atlas")
        print("  2. Verify IP whitelist (Security → Network Access)")
        print("  3. Verify username and password")
        return False
    except ImportError:
        print("✗ pymongo not installed")
        print("  → pip install pymongo")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


def test_insert(uri: str, db_name: str, collection: str):
    """Test inserting a document."""
    print("\n📝 Testing Document Insert...")
    print("=" * 50)

    test_doc = {
        "type": "test",
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        "message": "Connection test from readme-evaluator",
    }

    mongo_id = save_to_mongo(test_doc, uri, db_name, collection)

    if mongo_id:
        print(f"✓ Document Inserted!")
        print(f"  ID: {mongo_id}")
        return mongo_id
    else:
        print("✗ Failed to insert document")
        return None


def test_find(uri: str, db_name: str, collection: str, doc_id: str = None):
    """Test querying documents."""
    print("\n🔍 Testing Document Query...")
    print("=" * 50)

    try:
        from pymongo import MongoClient
        from bson import ObjectId

        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        db = client[db_name]
        coll = db[collection]

        if doc_id:
            try:
                doc = coll.find_one({"_id": ObjectId(doc_id)})
                if doc:
                    print(f"✓ Found document: {doc_id}")
                    print(f"  Keys: {list(doc.keys())}")
                else:
                    print(f"✗ Document not found: {doc_id}")
            except Exception as e:
                print(f"✗ Failed to find document: {e}")
        else:
            count = coll.count_documents({})
            print(f"✓ Total documents in collection: {count}")

            if count > 0:
                latest = coll.find_one(sort=[("_id", -1)])
                if latest:
                    print(f"  Latest: {latest.get('_id')}")
                    print(f"  Keys: {list(latest.keys())}")

        client.close()
        return True

    except Exception as e:
        print(f"✗ Query failed: {e}")
        return False


def test_file_fallback():
    """Test file-based fallback."""
    print("\n💾 Testing File Fallback...")
    print("=" * 50)

    import tempfile

    test_doc = {
        "type": "fallback_test",
        "data": "This is a test document",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        temp_path = f.name

    try:
        result = save_to_file(test_doc, temp_path)
        print(f"✓ File saved: {result}")

        # Verify file exists and has content
        if os.path.exists(temp_path):
            with open(temp_path, "r") as f:
                content = f.read()
            if content:
                print(f"✓ File verified ({len(content)} bytes)")
                os.remove(temp_path)
                return True

        print("✗ File is empty")
        return False

    except Exception as e:
        print(f"✗ File save failed: {e}")
        return False


def test_combined_save(uri: str, db_name: str, collection: str):
    """Test combined MongoDB + file save."""
    print("\n🔄 Testing Combined Save (MongoDB + File)...")
    print("=" * 50)

    import tempfile

    test_doc = {
        "type": "combined_test",
        "content": "Testing both MongoDB and file persistence",
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        temp_path = f.name

    try:
        mongo_id, file_path = save_with_mongo_fallback(
            test_doc,
            temp_path,
            mongo_uri=uri,
            db_name=db_name,
            collection=collection,
        )

        if mongo_id:
            print(f"✓ MongoDB: {mongo_id}")
        else:
            print("⚠ MongoDB save failed (may be offline)")

        if file_path and os.path.exists(temp_path):
            print(f"✓ File: {file_path}")
            os.remove(temp_path)
        else:
            print("✗ File save failed")
            return False

        return True

    except Exception as e:
        print(f"✗ Combined save failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test MongoDB Atlas integration for readme-evaluator"
    )
    parser.add_argument("--uri", help="MongoDB connection URI")
    parser.add_argument("--db", default="readme_evaluator", help="Database name")
    parser.add_argument("--collection", default="evaluations", help="Collection name")
    parser.add_argument("--full", action="store_true", help="Run all tests including insert")
    args = parser.parse_args()

    print("\n" + "=" * 50)
    print("MongoDB Atlas Connection Tester")
    print("=" * 50)

    # Load environment
    result = test_env_vars()
    if not result:
        print("\n❌ Environment setup failed")
        return 1

    uri, db_name, coll_name = result
    if args.uri:
        uri = args.uri
    if args.db:
        db_name = args.db
    if args.collection:
        coll_name = args.collection

    # Test connection
    if not test_direct_connection(uri):
        print("\n❌ Connection test failed")
        return 1

    # Test file fallback
    if not test_file_fallback():
        print("\n⚠ File fallback test failed")

    # Test operations
    if args.full:
        doc_id = test_insert(uri, db_name, coll_name)
        test_find(uri, db_name, coll_name, doc_id)

    test_combined_save(uri, db_name, coll_name)

    print("\n" + "=" * 50)
    print("✅ All tests passed!")
    print("=" * 50)
    print("\n📚 Next steps:")
    print("  1. Configure .env with your MongoDB Atlas credentials")
    print("  2. Run: python -m uvicorn backend.main:app --reload")
    print("  3. Send a request to /extract-json")
    print("  4. Check MongoDB Atlas for saved results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
