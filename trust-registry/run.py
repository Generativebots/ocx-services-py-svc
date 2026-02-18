#!/usr/bin/env python3
"""
OCX Trust Registry Service
--------------------------
Main entry point for the Trust Registry service.

Usage:
    python run.py [--port PORT] [--reload]
    
Environment variables:
    PORT: Server port (default: 8000)
    SUPABASE_URL: Supabase URL
    SUPABASE_SERVICE_KEY: Supabase service key
"""

import os
import sys
import argparse
import logging
logger = logging.getLogger(__name__)

# Ensure local modules (jury.py, ledger.py, orchestrator.py) resolve
# before sibling packages (jury/, ledger/) in the parent directory
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)
# Add parent directory for shared imports
sys.path.insert(1, os.path.dirname(_this_dir))

def main() -> None:
    parser = argparse.ArgumentParser(description="OCX Trust Registry Service")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()
    
    import uvicorn
    from main import app

    
    print(f"🚀 Starting OCX Trust Registry on {args.host}:{args.port}")
    uvicorn.run(
        "main:app" if args.reload else app,
        host=args.host,
        port=args.port,
        reload=args.reload
    )

if __name__ == "__main__":
    main()
