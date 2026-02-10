#!/usr/bin/env bash
# =============================================================================
# OCX Proto Codegen — Generate Python stubs from .proto files
#
# Prerequisites:
#   pip install grpcio-tools
#
# Usage:
#   ./generate_protos.sh
#
# This compiles the .proto files from the Go backend into Python stubs.
# The hand-written stubs in proto/ are used as fallback when protoc is
# not available, but this script produces the real protobuf bindings.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROTO_SRC="${SCRIPT_DIR}/../../ocx-backend-go-svc/ocx-backend-go-svc/pb"
PROTO_OUT="${SCRIPT_DIR}/proto"

echo "📦 OCX Proto Codegen"
echo "   Source: ${PROTO_SRC}"
echo "   Output: ${PROTO_OUT}"

# Ensure output directory exists
mkdir -p "${PROTO_OUT}"

# Check if grpcio-tools is installed
if ! python3 -c "import grpc_tools" 2>/dev/null; then
    echo "❌ grpcio-tools not installed. Run: pip install grpcio-tools"
    exit 1
fi

# Compile jury.proto
echo "🔧 Compiling jury.proto..."
python3 -m grpc_tools.protoc \
    -I"${PROTO_SRC}" \
    -I"${PROTO_SRC}/jury" \
    --python_out="${PROTO_OUT}" \
    --grpc_python_out="${PROTO_OUT}" \
    "${PROTO_SRC}/jury/jury.proto"

# Compile ledger.proto (needs google/protobuf for Timestamp)
echo "🔧 Compiling ledger.proto..."
python3 -m grpc_tools.protoc \
    -I"${PROTO_SRC}" \
    --python_out="${PROTO_OUT}" \
    --grpc_python_out="${PROTO_OUT}" \
    "${PROTO_SRC}/ledger.proto"

# Compile escrow.proto
echo "🔧 Compiling escrow.proto..."
python3 -m grpc_tools.protoc \
    -I"${PROTO_SRC}" \
    --python_out="${PROTO_OUT}" \
    --grpc_python_out="${PROTO_OUT}" \
    "${PROTO_SRC}/escrow.proto"

# Compile traffic_assessment.proto
echo "🔧 Compiling traffic_assessment.proto..."
python3 -m grpc_tools.protoc \
    -I"${PROTO_SRC}" \
    --python_out="${PROTO_OUT}" \
    --grpc_python_out="${PROTO_OUT}" \
    "${PROTO_SRC}/traffic_assessment.proto"

echo "✅ Proto codegen complete! Generated files in ${PROTO_OUT}:"
ls -la "${PROTO_OUT}"/*.py
