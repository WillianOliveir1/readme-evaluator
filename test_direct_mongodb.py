#!/usr/bin/env python
"""
Simple direct test: Save a document to MongoDB without using the web server

This tests if MongoDB connection is working independently of the web server.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
_proj_root = Path(__file__).resolve().parent
load_dotenv(_proj_root / ".env")

def test_direct_save():
    """Test saving directly to MongoDB"""
    
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB", "readme_evaluator")
    collection_name = os.getenv("MONGODB_COLLECTION", "evaluations")
    
    print("=" * 80)
    print("DIRECT MONGODB SAVE TEST")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  URI: {uri[:60] if uri else 'NOT SET'}...")
    print(f"  Database: {db_name}")
    print(f"  Collection: {collection_name}")
    
    if not uri:
        print("\n❌ MONGODB_URI not configured in .env")
        return False
    
    # Try to save
    print(f"\n📝 Saving test document...")
    
    try:
        from pymongo import MongoClient
        import datetime
        
        # Connect
        print("   Connecting to MongoDB...")
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
        
        # Verify connection
        print("   Pinging MongoDB...")
        client.admin.command("ping")
        print("   ✅ Connected!")
        
        # Get collection
        db = client[db_name]
        coll = db[collection_name]
        
        # Create test document
        test_doc = {
            "test_type": "direct_save",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "message": "This is a direct test document",
            "parsed": {
                "what": {
                    "score": 9,
                    "description": "Test successful"
                }
            }
        }
        
        # Insert
        print("   Inserting document...")
        result = coll.insert_one(test_doc)
        doc_id = str(result.inserted_id)
        print(f"   ✅ Inserted with ID: {doc_id}")
        
        # Verify
        print(f"   Verifying...")
        found = coll.find_one({"_id": result.inserted_id})
        if found:
            print(f"   ✅ Document verified in collection!")
            print(f"\n✅ SUCCESS! MongoDB is working correctly.")
            print(f"\n📊 Collection stats:")
            count = coll.count_documents({})
            print(f"   Total documents: {count}")
        else:
            print(f"   ❌ Document not found after insert")
            return False
        
        client.close()
        return True
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_direct_save()
    exit(0 if success else 1)
