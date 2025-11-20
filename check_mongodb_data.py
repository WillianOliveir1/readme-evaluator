#!/usr/bin/env python
"""Test MongoDB saving after using /extract-json-stream"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env
_proj_root = Path(__file__).resolve().parent
load_dotenv(_proj_root / ".env")

def check_mongodb():
    """Check if data was saved to MongoDB"""
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB", "readme_evaluator")
    collection_name = os.getenv("MONGODB_COLLECTION", "evaluations")
    
    if not uri:
        print("❌ MONGODB_URI not configured")
        return
    
    print(f"🔍 Checking MongoDB connection...")
    print(f"   URI: {uri[:50]}...")
    print(f"   Database: {db_name}")
    print(f"   Collection: {collection_name}")
    
    try:
        from pymongo import MongoClient
        
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
        
        # Test connection
        client.admin.command("ping")
        print("✅ Connected to MongoDB Atlas")
        
        # Get database and collection
        db = client[db_name]
        coll = db[collection_name]
        
        # Count documents
        count = coll.count_documents({})
        print(f"\n📊 Documents in collection: {count}")
        
        if count > 0:
            # Show latest documents
            print("\n📝 Latest 3 documents:")
            for i, doc in enumerate(coll.find().sort("_saved_at", -1).limit(3), 1):
                print(f"\n   Document {i}:")
                print(f"   - ID: {doc.get('_id')}")
                print(f"   - Saved at: {doc.get('_saved_at')}")
                if 'parsed' in doc:
                    print(f"   - Has parsed JSON: ✓")
                if 'model_output' in doc:
                    print(f"   - Has model output: ✓")
        else:
            print("\n⚠️  No documents found. Run an evaluation via frontend first.")
        
        client.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_mongodb()
