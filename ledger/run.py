#!/usr/bin/env python3
"""
OCX Ledger Service
------------------
Main entry point for the immutable governance ledger.

Usage:
    python run.py [--port PORT]
    
Environment variables:
    PORT: Server port (default: 8007)
    SUPABASE_URL: Supabase URL
    SUPABASE_SERVICE_KEY: Supabase service key
"""

import os
import sys
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    parser = argparse.ArgumentParser(description="OCX Ledger Service")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8007")))
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    args = parser.parse_args()
    
    from fastapi import FastAPI
    from immutable_ledger import ImmutableGovernanceLedger
    from supabase_client import SupabaseLedgerClient
    import uvicorn
    
    # Initialize components
    supabase_client = SupabaseLedgerClient()
    ledger = ImmutableGovernanceLedger(supabase_client=supabase_client)
    
    app = FastAPI(title="OCX Governance Ledger")
    
    @app.get("/health")
    def health():
        return {"status": "ok", "service": "ledger"}
    
    @app.get("/ledger/verify")
    def verify_chain():
        is_valid = ledger.verify_chain()
        return {"chain_valid": is_valid}
    
    @app.get("/ledger/stats")
    def get_stats():
        entries = supabase_client.query_all()
        return {"total_entries": len(entries)}
    
    print(f"📒 Starting OCX Ledger on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
