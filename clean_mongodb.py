"""Clean MongoDB collection and prepare for fresh testing.

Execute este script para limpar a coleção de testes:
    python clean_mongodb.py
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    print(f"⚠ .env file not found at: {env_path}")
    sys.exit(1)

from backend.db.mongodb_handler import MongoDBHandler
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)


def main():
    print("\n" + "=" * 80)
    print("MongoDB Collection Cleaner")
    print("=" * 80)
    
    try:
        handler = MongoDBHandler()
        
        print(f"\n📍 Database: {handler.db_name}")
        print(f"📍 Collection: {handler.collection_name}")
        
        # Count existing documents
        total = handler.count_documents()
        print(f"\n📊 Current documents in collection: {total}")
        
        if total == 0:
            print("\n✓ Collection is already empty")
            handler.disconnect()
            return
        
        # Show some documents
        print("\nExisting documents:")
        docs = handler.find_all()
        for idx, doc in enumerate(docs[:5], 1):
            title = doc.get('title') or doc.get('parsed', {}).get('metadata', {}).get('repository_name', 'Unknown')
            print(f"  {idx}. {title}")
        
        if len(docs) > 5:
            print(f"  ... and {len(docs) - 5} more")
        
        # Ask for confirmation
        print("\n" + "-" * 80)
        confirm = input("Delete ALL documents in this collection? (type 'yes' to confirm): ").strip()
        
        if confirm.lower() != 'yes':
            print("\nDeletion cancelled")
            handler.disconnect()
            return
        
        # Delete all documents
        deleted = handler.delete_all()
        print(f"\n✓ Deleted {deleted} document(s)")
        
        # Verify
        remaining = handler.count_documents()
        print(f"✓ Remaining documents: {remaining}")
        
        if remaining == 0:
            print("\n✅ Collection is now clean and ready for fresh data!")
        
        handler.disconnect()
        
    except Exception as e:
        LOG.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
