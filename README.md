# ocx-services-py-svc

Python cognitive services for the OCX Autonomous Operational Control System (AOCS).

## Services

| Service | Port | Protocol | Description |
|---------|------|----------|-------------|
| **Trust Registry** | 8000 | REST | Policy engine, APE orchestration, JSON-Logic evaluation |
| **Jury** | 50051 | gRPC | Multi-agent cognitive auditor & trust scoring |
| **Evidence Vault** | 8004 | REST | Immutable evidence chains & attestations |
| **Governance Ledger** | 8007 | REST | Blockchain-backed transaction audit |
| **Authority** | 8005 | REST | Automated Policy Extraction (APE) engine |
| **Activity Registry** | 8003 | REST | EBCL activity lifecycle management |

## Prerequisites

- Python 3.11+
- PostgreSQL (Supabase)

## Quick Start

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start a service (e.g., Trust Registry)
cd trust-registry && python run.py --port 8000
```

## Docker

Each service has its own `Dockerfile`:

```bash
# Build Trust Registry
docker build -t ocx-trust-registry -f trust-registry/Dockerfile .

# Run
docker run -p 8000:8000 --env-file .env ocx-trust-registry
```

## Environment

Copy `.env.example` to `.env` and configure:

```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
JURY_PORT=50051
```
