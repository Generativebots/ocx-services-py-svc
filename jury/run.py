#!/usr/bin/env python3
"""
OCX Jury gRPC Service
---------------------
Main entry point for the Jury service.

Usage:
    python run.py [--port PORT]
    
Environment variables:
    JURY_PORT: gRPC server port (default: 50051)
    VLLM_BASE_URL: vLLM endpoint for LLM inference
"""

import os
import sys
import argparse
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main() -> None:
    parser = argparse.ArgumentParser(description="OCX Jury gRPC Service")
    parser.add_argument("--port", type=int, default=int(os.getenv("JURY_PORT", "50051")))
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    from grpc_server import serve
    
    print(f"⚖️  Starting OCX Jury gRPC Service on port {args.port}")
    serve(port=args.port)

if __name__ == "__main__":
    main()
