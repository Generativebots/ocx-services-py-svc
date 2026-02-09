#!/usr/bin/env python3
"""
OCX Authority Service
---------------------
Main entry point for the APE (Automated Policy Extraction) engine.

Usage:
    python run.py [--port PORT]
    
Environment variables:
    PORT: Server port (default: 8005)
"""

import os
import sys
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    parser = argparse.ArgumentParser(description="OCX Authority Service")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8005")))
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    args = parser.parse_args()
    
    from fastapi import FastAPI
    import uvicorn
    
    app = FastAPI(title="OCX Authority (APE Engine)")
    
    @app.get("/health")
    def health():
        return {"status": "ok", "service": "authority"}
    
    @app.get("/policies")
    def list_policies():
        """List active policies"""
        return {"policies": []}
    
    print(f"📜 Starting OCX Authority on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
