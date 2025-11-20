#!/usr/bin/env python
"""
Monitor script: Watches for MongoDB save operations in server logs

Shows which documents are being saved and their IDs.
This helps verify the /extract-json-stream endpoint is actually saving data.
"""

import os
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load .env
_proj_root = Path(__file__).resolve().parent
load_dotenv(_proj_root / ".env")

def check_recent_saves():
    """Check for recent MongoDB saves by querying the database"""
    
    uri = os.getenv("MONGODB_URI")
    if not uri:
        print("❌ MONGODB_URI not configured")
        return
    
    print("=" * 80)
    print("MONGODB SAVE MONITOR")
    print("=" * 80)
    print(f"\nChecking for recent saves in MongoDB...")
    
    try:
        from pymongo import MongoClient
        from datetime import datetime, timedelta
        
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        
        db = client["readme_evaluator"]
        coll = db["evaluations"]
        
        # Get last 5 documents
        recent = list(coll.find().sort("_saved_at", -1).limit(5))
        
        if not recent:
            print("\n⚠️  No documents found in collection yet.")
            print("   Run an evaluation from the frontend first.")
            client.close()
            return
        
        print(f"\n✅ Found {len(recent)} recent documents:\n")
        
        for i, doc in enumerate(recent, 1):
            print(f"Document {i}:")
            print(f"  ID: {doc.get('_id')}")
            print(f"  Saved at: {doc.get('_saved_at')}")
            
            # Show structure
            if 'parsed' in doc:
                print(f"  ✓ Has parsed JSON")
                what = doc.get('parsed', {}).get('what', {})
                if what:
                    print(f"    - What score: {what.get('score', 'N/A')}")
            
            if 'model_output' in doc:
                model_out = doc.get('model_output', '')
                if model_out:
                    print(f"  ✓ Has model output ({len(model_out)} chars)")
            
            if 'validation_ok' in doc:
                print(f"  ✓ Validation: {doc.get('validation_ok')}")
            
            print()
        
        # Summary
        total = coll.count_documents({})
        
        # Get oldest and newest
        oldest = coll.find_one(sort=[("_saved_at", 1)])
        newest = coll.find_one(sort=[("_saved_at", -1)])
        
        print(f"📊 Summary:")
        print(f"  Total documents: {total}")
        if oldest and newest:
            print(f"  Oldest: {oldest.get('_saved_at')}")
            print(f"  Newest: {newest.get('_saved_at')}")
        
        client.close()
        print("\n✅ Connection successful!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_recent_saves()
