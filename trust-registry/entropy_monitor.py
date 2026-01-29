import math
from collections import Counter
from typing import List

class EntropyMonitor:
    def __init__(self):
        pass

    def calculate_shannon_entropy(self, data_points: List[float]) -> float:
        """
        Calculates the Shannon Entropy of a dataset (handshake intervals).
        Higher values = natural variance (Healthy).
        Lower values = high predictability (Collusion/Looping).
        """
        if not data_points:
            return 0.0
        
        # Round to 2 decimals to create "buckets" for the probability distribution
        counts = Counter([round(x, 2) for x in data_points])
        total_samples = len(data_points)
        
        entropy = 0.0
        for count in counts.values():
            probability = count / total_samples
            # Shannon Entropy formula: -sum(p * log2(p))
            entropy -= probability * math.log2(probability)
            
        return entropy

    def assess_health(self, entropy_score: float) -> str:
        """
        Returns a status based on Month 3 thresholds.
        """
        if entropy_score > 2.0:
            return "HEALTHY"
        elif entropy_score < 0.8:
            return "CRITICAL_COLLUSION_RISK"
        else:
            return "WARNING_LOW_ENTROPY"

# --- Simulation for Verification ---
def simulate_traffic():
    monitor = EntropyMonitor()
    
    # 1. Healthy Traffic (Random Jitter)
    import random
    healthy_data = [random.uniform(0.05, 0.5) for _ in range(50)]
    h_score = monitor.calculate_shannon_entropy(healthy_data)
    print(f"Healthy Sample Entropy: {h_score:.4f} bits -> {monitor.assess_health(h_score)}")
    
    # 2. Collusion Traffic (Fixed Interval)
    collusion_data = [0.10 for _ in range(50)]
    c_score = monitor.calculate_shannon_entropy(collusion_data)
    print(f"Collusion Sample Entropy: {c_score:.4f} bits -> {monitor.assess_health(c_score)}")

if __name__ == "__main__":
    simulate_traffic()
