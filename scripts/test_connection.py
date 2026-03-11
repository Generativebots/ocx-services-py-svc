#!/usr/bin/env python3
"""
Test Supabase connection for Python services
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

def test_connection() -> bool:
    print("=" * 50)
    print("OCX Python Services - Supabase Connection Test")
    print("=" * 50)
    print()
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not url or not key:
        print("❌ SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
        return False
    
    print(f"SUPABASE_URL: {url}")
    print(f"SUPABASE_SERVICE_KEY: {key[:20]}...")
    print()
    
    try:
        # Create client
        supabase: Client = create_client(url, key)
        print("✅ Supabase client created successfully!")
        
        # Test query
        result = supabase.table("tenants").select("tenant_id, tenant_name, subscription_tier").limit(5).execute()
        
        print()
        print("✅ Retrieved tenants:")
        for tenant in result.data:
            print(f"   - {tenant['tenant_name']} ({tenant['subscription_tier']})")
        
        print()
        print("=" * 50)
        print("✅ Python services ↔ Supabase connection verified!")
        print("=" * 50)
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_connection()
