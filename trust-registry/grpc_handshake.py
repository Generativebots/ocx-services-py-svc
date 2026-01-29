import grpc
import hashlib
import json
import logging

# Note: These imports require running `python -m grpc_tools.protoc ...` to generate the pb2 files
# from backend/pb/traffic_assessment.proto
try:
    import traffic_assessment_pb2
    import traffic_assessment_pb2_grpc
except ImportError:
    logging.warning("Protobuf files not generated. Run protoc to enable gRPC communication.")
    # Mocks for static analysis / development without protoc
    class MockPB2:
        ExecutionPlan = dict
    class MockPB2GRPC:
        PlanServiceStub = lambda x: MockStub()
    class MockStub:
        def RegisterIntent(self, plan):
             return type('Response', (object,), {"message": "Mock Success"})()
    traffic_assessment_pb2 = MockPB2()
    traffic_assessment_pb2_grpc = MockPB2GRPC()

class HandshakeOrchestrator:
    """
    Acts as 'The Brain' (Python Orchestrator Handshake).
    Predicts agent actions, hashes the intent, and registers the plan with the Go Gateway.
    """
    def __init__(self, gateway_address='localhost:50051'):
        self.channel = grpc.insecure_channel(gateway_address)
        self.stub = traffic_assessment_pb2_grpc.PlanServiceStub(self.channel)

    def generate_expected_hash(self, predicted_changes):
        """
        Creates a SHA-256 fingerprint of what the AI predicts will happen.
        predicted_changes: A dict of expected file/DB/network changes.
        """
        serialized_intent = json.dumps(predicted_changes, sort_keys=True).encode('utf-8')
        return hashlib.sha256(serialized_intent).hexdigest()

    def send_plan_to_gateway(self, agent_id, intent_data, manual_review=False):
        """
        Registers the execution plan with the Nervous System (Go Gateway).
        """
        # 1. Predict the outcome (This would come from the LLM/Intent Analysis)
        # For this handshake demo, we construct the outcome from intent_data or use defaults
        expected_outcome = intent_data if intent_data else {
            "action": "file_write",
            "path": "/tmp/results.json",
            "status": "success"
        }
        
        # 2. Generate the Hash (The "Expectation")
        # This hash represents the "Immutable Record" of what was approved.
        outcome_hash = self.generate_expected_hash(expected_outcome)

        # 3. Build the gRPC Plan Manifest
        # The ManualReviewRequired boolean switch is set here.
        plan = traffic_assessment_pb2.ExecutionPlan(
            plan_id="plan_" + agent_id,
            agent_id=agent_id,
            allowed_calls=["sys_write", "sys_open"], # In reality, deduced from intent
            expected_outcome_hash=outcome_hash,
            manual_review_required=manual_review 
        )

        # 4. The Handshake: Register intent with the Go Nervous System
        try:
            print(f"🤝 [Handshake] Sending Plan for {agent_id} (ManualReview={manual_review})...")
            response = self.stub.RegisterIntent(plan)
            print(f"✅ [Handshake] Successful: {response.message}")
            return True
        except grpc.RpcError as e:
            print(f"❌ [Handshake] Failed: {e.details()}")
            return False

# Example Usage
if __name__ == "__main__":
    # Simulate the Orchestrator sending a plan
    orchestrator = HandshakeOrchestrator()
    
    # Scene 1: Low-Risk Task (Auto-Commit)
    orchestrator.send_plan_to_gateway("agent_007", {"task": "report_gen"}, manual_review=False)
    
    # Scene 2: High-Risk Task (Manual Review)
    orchestrator.send_plan_to_gateway("agent_007", {"task": "delete_db"}, manual_review=True)
