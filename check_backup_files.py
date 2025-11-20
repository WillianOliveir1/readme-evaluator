#!/usr/bin/env python
"""
Check backup files created

Shows all backup files in processed/ directory with their timestamps and sizes.
"""

import os
import json
from pathlib import Path
from datetime import datetime

def main():
    print("=" * 100)
    print("BACKUP FILES CHECK")
    print("=" * 100)
    
    processed_dir = Path(".") / "processed"
    
    print(f"\n📂 Looking in: {processed_dir.resolve()}")
    
    if not processed_dir.exists():
        print(f"   ✗ Directory does not exist!")
        return
    
    # Find all .jsonl files
    backup_files = list(processed_dir.glob("*.jsonl"))
    
    if not backup_files:
        print(f"   ✗ No backup files (.jsonl) found")
        return
    
    print(f"   ✓ Found {len(backup_files)} backup file(s)\n")
    
    for filepath in sorted(backup_files, reverse=True):  # Newest first
        file_size = filepath.stat().st_size
        file_mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
        
        print(f"📄 {filepath.name}")
        print(f"   Size: {file_size / 1024:.2f} KB")
        print(f"   Created: {file_mtime.isoformat()}")
        
        # Try to read and show a preview
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                line = f.readline()
                if line:
                    data = json.loads(line)
                    
                    # Extract document (it's wrapped)
                    if 'document' in data:
                        doc = data['document']
                    else:
                        doc = data
                    
                    # Show what's in it
                    print(f"   Content preview:")
                    if doc.get('parsed') and doc['parsed'].get('metadata'):
                        repo = doc['parsed']['metadata'].get('repository_name', 'unknown')
                        print(f"      - Repository: {repo}")
                    
                    if doc.get('success'):
                        print(f"      - Success: ✓")
                    
                    if doc.get('mongo_id'):
                        print(f"      - MongoDB ID: {doc['mongo_id']}")
                        print(f"      ✓ THIS WAS SAVED TO MONGODB!")
                    else:
                        print(f"      - MongoDB ID: None")
                        print(f"      ✗ NOT SAVED TO MONGODB (only file backup)")
        except Exception as e:
            print(f"   Error reading file: {e}")
        
        print()

if __name__ == "__main__":
    main()
