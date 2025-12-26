#!/usr/bin/env python3
"""
Notion Diagnostic Script
Tests Notion API connection and configuration.
"""

import os
import sys
from pathlib import Path

# Load environment variables from .env file (same as main bot)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[DIAG] ⚠️ python-dotenv not installed, reading from environment only")
    print("[DIAG] Install with: pip install python-dotenv")

# Check if notion-client is available
try:
    from notion_client import Client
    NOTION_CLIENT_AVAILABLE = True
except ImportError:
    NOTION_CLIENT_AVAILABLE = False
    print("[DIAG] ❌ notion-client not installed")
    print("[DIAG] Install with: pip install notion-client")
    sys.exit(1)

# Get environment variables
api_key = os.getenv("NOTION_API_KEY")
database_id = os.getenv("NOTION_DATABASE_ID")

# Print status
print("=" * 60)
print("NOTION DIAGNOSTIC REPORT")
print("=" * 60)

print(f"\n[1] NOTION_API_KEY present: {'yes' if api_key else 'no'}")
if api_key:
    print(f"    Key starts with: {api_key[:10]}...")
else:
    print("    ⚠️ Missing! Add NOTION_API_KEY to .env file")

print(f"\n[2] NOTION_DATABASE_ID present: {'yes' if database_id else 'no'}")
if database_id:
    print(f"    Database ID: {database_id}")
else:
    print("    ⚠️ Missing! Add NOTION_DATABASE_ID to .env file")

# If both are present, test connection
if api_key and database_id:
    print("\n[3] Testing connection...")
    try:
        client = Client(auth=api_key)
        # Try to retrieve the database
        result = client.databases.retrieve(database_id=database_id)
        
        # Success!
        db_title = "Unknown"
        if result.get("title"):
            titles = result["title"]
            if isinstance(titles, list) and len(titles) > 0:
                db_title = titles[0].get("plain_text", "Unknown")
        
        print("    ✅ OK: token and database are valid.")
        print(f"    Database title: {db_title}")
        print(f"    Database ID: {database_id}")
        
    except Exception as e:
        error_str = str(e).lower()
        
        if "unauthorized" in error_str or "401" in error_str:
            print("    ❌ ERROR: unauthorized (check token or integration share to database)")
            print("    → Go to: https://www.notion.so/my-integrations")
            print("    → Verify your integration 'Bot Task Automator' exists")
            print("    → Check that the integration has access to your database")
            print("    → Copy the correct API token")
            
        elif "not found" in error_str or "404" in error_str:
            print("    ❌ ERROR: database not found (check NOTION_DATABASE_ID)")
            print("    → Verify your database ID: 2d36e908b8a180a992abd323fddaf04f")
            print("    → Check that the database exists and is accessible")
            
        else:
            print(f"    ❌ ERROR: {e}")
            print("    → Check your API token and database ID")
            print("    → Verify network connectivity")
        
        sys.exit(1)
else:
    print("\n[3] Skipping connection test (missing credentials)")
    print("\nTo fix:")
    print("1. Copy .env.example to .env:")
    print("   cp .env.example .env")
    print("2. Edit .env and add your values:")
    print("   NOTION_API_KEY=your_token_here")
    print("   NOTION_DATABASE_ID=your_database_id_here")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ DIAGNOSTIC COMPLETE - NOTION IS CONFIGURED CORRECTLY")
print("=" * 60)

