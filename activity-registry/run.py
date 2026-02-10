#!/usr/bin/env python3
"""
OCX Activity Registry Service
-----------------------------
Main entry point for the Activity Registry service.

Usage:
    python run.py [--port PORT]
    
Environment variables:
    PORT: Server port (default: 8003)
"""

import os
import sys
import argparse
import logging
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main() -> None:
    parser = argparse.ArgumentParser(description="OCX Activity Registry Service")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8003")))
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    args = parser.parse_args()
    
    from fastapi import FastAPI
    import uvicorn

    
    app = FastAPI(title="OCX Activity Registry")
    
    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "activity-registry"}
    
    @app.get("/activities")
    def list_activities() -> dict:
        """List recent activities"""
        return {"activities": []}
    
    print(f"📋 Starting OCX Activity Registry on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
