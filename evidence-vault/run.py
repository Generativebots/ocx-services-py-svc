#!/usr/bin/env python3
"""
OCX Evidence Vault Service
--------------------------
Main entry point for the Evidence Vault service.

Usage:
    python run.py [--port PORT]
    
Environment variables:
    PORT: Server port (default: 8004)
    SUPABASE_URL: Supabase URL
    SUPABASE_SERVICE_KEY: Supabase service key
"""

import os
import sys
import argparse
import logging
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main() -> None:
    parser = argparse.ArgumentParser(description="OCX Evidence Vault Service")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8004")))
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    args = parser.parse_args()
    
    import uvicorn
    from api import app

    
    print(f"🔐 Starting OCX Evidence Vault on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
