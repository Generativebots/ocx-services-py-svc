"""
Prometheus Metrics for APE Engine
Tracks extraction time, evaluation latency, and policy performance
"""

from prometheus_client import Counter, Histogram, Gauge, Summary
import time
from functools import wraps
import logging
logger = logging.getLogger(__name__)


# Extraction metrics
policy_extractions_total = Counter(
    'ape_policy_extractions_total',
    'Total number of policy extractions',
    ['source_name', 'model', 'status']
)

policy_extraction_duration = Histogram(
    'ape_policy_extraction_duration_seconds',
    'Time taken to extract policies from document',
    ['source_name', 'model'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

policies_extracted = Histogram(
    'ape_policies_extracted_count',
    'Number of policies extracted per document',
    ['source_name'],
    buckets=[1, 5, 10, 20, 50, 100]
)

extraction_confidence = Histogram(
    'ape_extraction_confidence',
    'Average confidence score of extracted policies',
    ['source_name'],
    buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0]
)

# Evaluation metrics
policy_evaluations_total = Counter(
    'ape_policy_evaluations_total',
    'Total number of policy evaluations',
    ['policy_id', 'tier', 'result']
)

policy_evaluation_duration = Histogram(
    'ape_policy_evaluation_duration_seconds',
    'Time taken to evaluate policy',
    ['policy_id', 'tier'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

policy_violations = Counter(
    'ape_policy_violations_total',
    'Total number of policy violations',
    ['policy_id', 'tier', 'action']
)

# Ghost-State metrics
ghost_state_simulations = Counter(
    'ape_ghost_state_simulations_total',
    'Total number of Ghost-State simulations',
    ['tool_name', 'result']
)

ghost_state_duration = Histogram(
    'ape_ghost_state_duration_seconds',
    'Time taken for Ghost-State simulation',
    ['tool_name'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1]
)

# Policy management metrics
active_policies = Gauge(
    'ape_active_policies',
    'Number of active policies',
    ['tier']
)

policy_versions = Gauge(
    'ape_policy_versions',
    'Number of versions per policy',
    ['policy_id']
)

policy_conflicts = Gauge(
    'ape_policy_conflicts',
    'Number of detected policy conflicts',
    ['conflict_type']
)

# Signal metrics
required_signals_collected = Counter(
    'ape_required_signals_collected_total',
    'Total number of required signals collected',
    ['signal_type', 'status']
)

signal_verification_duration = Histogram(
    'ape_signal_verification_duration_seconds',
    'Time taken to verify required signals',
    ['signal_type'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

# Model performance metrics
model_inference_duration = Histogram(
    'ape_model_inference_duration_seconds',
    'Time taken for LLM inference',
    ['model_name'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

model_errors = Counter(
    'ape_model_errors_total',
    'Total number of model errors',
    ['model_name', 'error_type']
)


# Decorators for automatic metric tracking
def track_extraction(source_name: str, model: str) -> None:
    """Decorator to track policy extraction metrics"""
    def decorator(func) -> None:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status = "success"
            
            try:
                result = func(*args, **kwargs)
                
                # Track number of policies extracted
                if isinstance(result, list):
                    policies_extracted.labels(source_name=source_name).observe(len(result))
                    
                    # Track average confidence
                    if result:
                        avg_conf = sum(p.get("confidence", 0) for p in result) / len(result)
                        extraction_confidence.labels(source_name=source_name).observe(avg_conf)
                
                return result
                
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                policy_extraction_duration.labels(
                    source_name=source_name,
                    model=model
                ).observe(duration)
                policy_extractions_total.labels(
                    source_name=source_name,
                    model=model,
                    status=status
                ).inc()
        
        return wrapper
    return decorator


def track_evaluation(policy_id: str, tier: str) -> None:
    """Decorator to track policy evaluation metrics"""
    def decorator(func) -> None:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                
                # Track result
                is_allowed = result[0] if isinstance(result, tuple) else result
                result_label = "allowed" if is_allowed else "blocked"
                
                policy_evaluations_total.labels(
                    policy_id=policy_id,
                    tier=tier,
                    result=result_label
                ).inc()
                
                # Track violations
                if not is_allowed:
                    action = result[1] if isinstance(result, tuple) and len(result) > 1 else "BLOCK"
                    policy_violations.labels(
                        policy_id=policy_id,
                        tier=tier,
                        action=action
                    ).inc()
                
                return result
                
            finally:
                duration = time.time() - start_time
                policy_evaluation_duration.labels(
                    policy_id=policy_id,
                    tier=tier
                ).observe(duration)
        
        return wrapper
    return decorator


def track_ghost_state(tool_name: str) -> None:
    """Decorator to track Ghost-State simulation metrics"""
    def decorator(func) -> None:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                
                # Track result
                is_allowed = result[0] if isinstance(result, tuple) else result
                result_label = "allowed" if is_allowed else "blocked"
                
                ghost_state_simulations.labels(
                    tool_name=tool_name,
                    result=result_label
                ).inc()
                
                return result
                
            finally:
                duration = time.time() - start_time
                ghost_state_duration.labels(tool_name=tool_name).observe(duration)
        
        return wrapper
    return decorator


# Example usage
if __name__ == "__main__":
    from prometheus_client import start_http_server
    
    # Start Prometheus metrics server
    start_http_server(8001)
    print("Prometheus metrics available at http://localhost:8001/metrics")
    
    # Simulate some metrics
    @track_extraction("Procurement SOP", "mistral-7b")
    def extract_policies() -> list:
        time.sleep(0.5)  # Simulate extraction
        return [
            {"policy_id": "P1", "confidence": 0.95},
            {"policy_id": "P2", "confidence": 0.88}
        ]
    
    @track_evaluation("PURCHASE_001", "CONTEXTUAL")
    def evaluate_policy() -> Any:
        time.sleep(0.01)  # Simulate evaluation
        return False, "BLOCK"
    
    # Run simulations
    for _ in range(10):
        extract_policies()
        evaluate_policy()
    
    print("Metrics updated. Check http://localhost:8001/metrics")
    
    # Keep server running
    import threading

    threading.Event().wait()
