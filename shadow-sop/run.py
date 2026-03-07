#!/usr/bin/env python3
"""
Process Mining / Shadow-SOP Service Runner

Usage:
    python run.py [--port PORT] [--host HOST]

Environment Variables:
    PORT:                 Server port (default: 8006)
    SUPABASE_URL:         Supabase project URL
    SUPABASE_SERVICE_KEY: Supabase service key
    CORS_ORIGINS:         Comma-separated CORS origins
    OCX_DEFAULT_TENANT:   Fallback tenant ID
"""
import argparse
import os
import sys

# Ensure shadow-sop package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description="OCX Process Mining / Shadow-SOP Service")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8006")))
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--workers", type=int,
                        default=int(os.getenv("UVICORN_WORKERS", "4")),
                        help="Number of uvicorn workers (default: UVICORN_WORKERS env or 4)")
    args = parser.parse_args()

    import uvicorn

    print(f"Starting Shadow-SOP / Process Mining service on {args.host}:{args.port} (workers={args.workers})")
    uvicorn.run("api:app", host=args.host, port=args.port, workers=args.workers)


if __name__ == "__main__":
    main()
