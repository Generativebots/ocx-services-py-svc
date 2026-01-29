# OCX Trust Calculation Service (Jury)

Python-based service implementing the weighted trust formula from the OCX patent.

## Formula

```
trust_level = (0.40 × audit_score) + 
              (0.30 × reputation_score) + 
              (0.20 × attestation_score) + 
              (0.10 × history_score)
```

## Trust Tax Calculation

```
trust_tax = (1.0 - trust_level) × 0.10 × transaction_value
```

**Examples:**
- Trust 1.0 → Tax 0% (perfect trust)
- Trust 0.85 → Tax 1.5%
- Trust 0.5 → Tax 5%
- Trust 0.0 → Tax 10%

## Installation

```bash
cd services/jury

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Generate protobuf files
python -m grpc_tools.protoc \
    -I../../proto \
    --python_out=. \
    --grpc_python_out=. \
    ../../proto/traffic_assessment.proto
```

## Running

```bash
# Start the Jury service
python trust_engine.py

# Or with custom port
python trust_engine.py --port 50051
```

## Architecture

```
┌─────────────────┐
│  Go Interceptor │
│   (eBPF/LSM)    │
└────────┬────────┘
         │ gRPC Stream
         │ TrafficEvent
         ▼
┌─────────────────┐
│  Python Jury    │
│  Trust Engine   │
├─────────────────┤
│ • Calculate     │
│   Trust Level   │
│ • Determine     │
│   Verdict       │
│ • Calculate     │
│   Trust Tax     │
└────────┬────────┘
         │ gRPC Stream
         │ AssessmentResponse
         ▼
┌─────────────────┐
│  Go Interceptor │
│  Verdict        │
│  Enforcer       │
└─────────────────┘
         │
         ▼
┌─────────────────┐
│  eBPF LSM Hook  │
│  Kernel         │
│  Enforcement    │
└─────────────────┘
```

## Components

### 1. TrustCalculationEngine
Core engine implementing the weighted trust formula.

```python
engine = TrustCalculationEngine()
scores = EntityScores(audit=0.9, reputation=0.8, attestation=0.7, history=0.6)
trust_level = await engine.calculate_trust(scores)
# Result: 0.81 (0.9*0.4 + 0.8*0.3 + 0.7*0.2 + 0.6*0.1)
```

### 2. IdentityDatabase
Stores and retrieves entity scores by binary hash.

In production, backed by:
- Redis (for speed)
- Cloud Spanner (for durability)

### 3. TrustCalculationService
gRPC service handling bidirectional streaming.

**Flow:**
1. Receive `TrafficEvent` from Go
2. Look up scores by `binary_sha256`
3. Calculate trust level
4. Determine verdict (ALLOW/BLOCK/HOLD)
5. Calculate trust tax
6. Stream `AssessmentResponse` back

## Configuration

Edit constants in `trust_engine.py`:

```python
WEIGHT_AUDIT = 0.40        # 40% weight
WEIGHT_REPUTATION = 0.30   # 30% weight
WEIGHT_ATTESTATION = 0.20  # 20% weight
WEIGHT_HISTORY = 0.10      # 10% weight

TRUST_THRESHOLD = 0.65     # Minimum for ALLOW
TRUST_TAX_RATE = 0.10      # 10% base tax
```

## Testing

```bash
# Unit tests
pytest tests/test_trust_engine.py

# Integration test with Go Interceptor
python tests/integration_test.py
```

## Metrics

The service tracks:
- Total assessments
- Allowed count
- Blocked count
- Held count
- Block rate

Access via:
```python
service = TrustCalculationService()
metrics = service.get_metrics()
```

## Production Deployment

### Docker

```bash
docker build -t ocx-jury:latest .
docker run -p 50051:50051 ocx-jury:latest
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ocx-jury
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: jury
        image: ocx-jury:latest
        ports:
        - containerPort: 50051
        env:
        - name: REDIS_URL
          value: "redis://redis-service:6379"
        - name: SPANNER_PROJECT
          value: "ocx-production"
```

## Integration with Go Interceptor

The Go Interceptor connects to this service:

```go
// In Go
client := NewJuryClient("localhost:50051")
stream, err := client.InspectTraffic(ctx)

// Send event
stream.Send(&TrafficEvent{
    RequestId: uuid.New().String(),
    Metadata: &EventMetadata{
        Pid: 1234,
        BinarySha256: "abc123...",
    },
})

// Receive verdict
response, err := stream.Recv()
if response.Verdict.Action == ACTION_BLOCK {
    enforcer.EnforceVerdict(pid, ActionBlock, response.Verdict.TrustLevel, response.Reasoning)
}
```

## Economic Model Integration

The trust tax calculated by this service feeds into:

1. **Billing System** - Charge agents based on trust deficit
2. **ROI Dashboard** - Show savings from blocking low-trust traffic
3. **Network Effects** - Redistribute tax to high-trust agents
4. **Governance** - Fund the Standards Committee

## Patent Alignment

This implementation directly fulfills:

✅ **Weighted Trust Calculation** - Core formula implemented  
✅ **Economic Model** - Trust tax calculation  
✅ **Active Blocking** - Real-time verdict enforcement  
✅ **Network Effects** - Foundation for value redistribution  

## License

Proprietary - OCX Protocol v2.0
