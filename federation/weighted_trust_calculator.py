"""
Weighted Trust Calculator Service - Integration Layer

Integrates all trust components:
- Audit verification (40%)
- Reputation scoring (30%)
- Attestation freshness (20%)
- Relationship history (10%)

Provides unified API for trust calculation across the OCX platform.
"""

from typing import Dict, Optional
from datetime import datetime


class WeightedTrustCalculator:
    """
    Calculates weighted trust scores using the OCX formula:
    
    trust_level = (0.40 × audit_score) + 
                  (0.30 × reputation_score) + 
                  (0.20 × attestation_score) + 
                  (0.10 × history_score)
    
    Each component is scored 0.0 - 1.0
    """
    
    # Weight constants
    AUDIT_WEIGHT = 0.40
    REPUTATION_WEIGHT = 0.30
    ATTESTATION_WEIGHT = 0.20
    HISTORY_WEIGHT = 0.10
    
    def __init__(self):
        self.calculations_performed = 0
        self.avg_trust_level = 0.0
    
    def calculate_trust(self, 
                       audit_score: float,
                       reputation_score: float,
                       attestation_score: float,
                       history_score: float) -> Dict:
        """
        Calculate weighted trust level
        
        Args:
            audit_score: Audit verification score (0.0 - 1.0)
            reputation_score: Historical reputation score (0.0 - 1.0)
            attestation_score: Attestation freshness score (0.0 - 1.0)
            history_score: Relationship history score (0.0 - 1.0)
        
        Returns:
            Dict with trust_level and component breakdown
        """
        # Validate inputs
        self._validate_score(audit_score, "audit_score")
        self._validate_score(reputation_score, "reputation_score")
        self._validate_score(attestation_score, "attestation_score")
        self._validate_score(history_score, "history_score")
        
        # Calculate weighted components
        audit_weighted = self.AUDIT_WEIGHT * audit_score
        reputation_weighted = self.REPUTATION_WEIGHT * reputation_score
        attestation_weighted = self.ATTESTATION_WEIGHT * attestation_score
        history_weighted = self.HISTORY_WEIGHT * history_score
        
        # Calculate total trust level
        trust_level = (audit_weighted + 
                      reputation_weighted + 
                      attestation_weighted + 
                      history_weighted)
        
        # Update statistics
        self.calculations_performed += 1
        self.avg_trust_level = ((self.avg_trust_level * (self.calculations_performed - 1)) + 
                               trust_level) / self.calculations_performed
        
        return {
            'trust_level': trust_level,
            'components': {
                'audit': {
                    'score': audit_score,
                    'weight': self.AUDIT_WEIGHT,
                    'weighted_value': audit_weighted,
                },
                'reputation': {
                    'score': reputation_score,
                    'weight': self.REPUTATION_WEIGHT,
                    'weighted_value': reputation_weighted,
                },
                'attestation': {
                    'score': attestation_score,
                    'weight': self.ATTESTATION_WEIGHT,
                    'weighted_value': attestation_weighted,
                },
                'history': {
                    'score': history_score,
                    'weight': self.HISTORY_WEIGHT,
                    'weighted_value': history_weighted,
                },
            },
            'metadata': {
                'calculated_at': datetime.utcnow().isoformat(),
                'formula': '0.40×audit + 0.30×reputation + 0.20×attestation + 0.10×history',
            }
        }
    
    def calculate_audit_score(self, audit_hash_verified: bool, 
                             signature_valid: bool,
                             certificate_valid: bool,
                             nonce_fresh: bool) -> float:
        """
        Calculate audit verification score
        
        Args:
            audit_hash_verified: Whether audit hash matches
            signature_valid: Whether signature is valid
            certificate_valid: Whether certificate is valid
            nonce_fresh: Whether nonce is fresh
        
        Returns:
            Audit score (0.0 - 1.0)
        """
        # All checks must pass for full score
        checks = [audit_hash_verified, signature_valid, certificate_valid, nonce_fresh]
        passed_checks = sum(checks)
        
        return passed_checks / len(checks)
    
    def calculate_reputation_score(self, 
                                  total_interactions: int,
                                  successful_interactions: int,
                                  failed_interactions: int,
                                  blacklisted: bool = False) -> float:
        """
        Calculate reputation score based on historical interactions
        
        Args:
            total_interactions: Total number of interactions
            successful_interactions: Number of successful interactions
            failed_interactions: Number of failed interactions
            blacklisted: Whether agent is blacklisted
        
        Returns:
            Reputation score (0.0 - 1.0)
        """
        if blacklisted:
            return 0.0
        
        if total_interactions == 0:
            return 0.5  # Neutral for new agents
        
        success_rate = successful_interactions / total_interactions
        
        # Apply confidence factor based on interaction count
        if total_interactions < 10:
            confidence = 0.5
        elif total_interactions < 100:
            confidence = 0.8
        elif total_interactions < 1000:
            confidence = 0.95
        else:
            confidence = 1.0
        
        # Blend with neutral score based on confidence
        return (confidence * success_rate) + ((1 - confidence) * 0.5)
    
    def calculate_attestation_score(self, attestation_age_hours: float, 
                                   expires_at: Optional[datetime] = None) -> float:
        """
        Calculate attestation freshness score
        
        Args:
            attestation_age_hours: Age of attestation in hours
            expires_at: Optional expiration datetime
        
        Returns:
            Attestation score (0.0 - 1.0)
        """
        # Check expiration
        if expires_at and datetime.utcnow() > expires_at:
            return 0.0
        
        # Score based on freshness
        if attestation_age_hours < 1:
            return 1.0
        elif attestation_age_hours < 24:
            return 0.8
        elif attestation_age_hours < 168:  # 7 days
            return 0.6
        elif attestation_age_hours < 720:  # 30 days
            return 0.4
        else:
            return 0.2
    
    def calculate_history_score(self, 
                               relationship_age_days: float,
                               total_interactions: int) -> float:
        """
        Calculate relationship history score
        
        Args:
            relationship_age_days: Age of relationship in days
            total_interactions: Total number of interactions
        
        Returns:
            History score (0.0 - 1.0)
        """
        # Age component
        if relationship_age_days > 365:
            age_score = 1.0
        elif relationship_age_days > 90:
            age_score = 0.8
        elif relationship_age_days > 30:
            age_score = 0.6
        elif relationship_age_days > 7:
            age_score = 0.4
        else:
            age_score = 0.2
        
        # Interaction count bonus
        if total_interactions > 1000:
            interaction_bonus = 0.2
        elif total_interactions > 100:
            interaction_bonus = 0.1
        elif total_interactions > 10:
            interaction_bonus = 0.05
        else:
            interaction_bonus = 0.0
        
        score = age_score + interaction_bonus
        return min(score, 1.0)  # Cap at 1.0
    
    def calculate_trust_tax(self, trust_level: float, base_rate: float = 0.10) -> float:
        """
        Calculate trust tax based on trust level
        
        Formula: tax = (1 - trust_level) × base_rate
        Higher trust = lower tax
        
        Args:
            trust_level: Trust level (0.0 - 1.0)
            base_rate: Base tax rate (default 10%)
        
        Returns:
            Trust tax percentage (0.0 - base_rate)
        """
        self._validate_score(trust_level, "trust_level")
        
        trust_tax = (1.0 - trust_level) * base_rate
        
        return min(trust_tax, base_rate)  # Cap at base rate
    
    def _validate_score(self, score: float, name: str):
        """Validate that a score is in valid range"""
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"{name} must be between 0.0 and 1.0, got {score}")
    
    def get_statistics(self) -> Dict:
        """Get calculator statistics"""
        return {
            'calculations_performed': self.calculations_performed,
            'avg_trust_level': self.avg_trust_level,
            'weights': {
                'audit': self.AUDIT_WEIGHT,
                'reputation': self.REPUTATION_WEIGHT,
                'attestation': self.ATTESTATION_WEIGHT,
                'history': self.HISTORY_WEIGHT,
            }
        }


# Example usage
if __name__ == "__main__":
    calculator = WeightedTrustCalculator()
    
    # Example 1: High trust scenario
    print("Example 1: High Trust Scenario")
    result = calculator.calculate_trust(
        audit_score=1.0,      # Perfect audit
        reputation_score=0.95,  # Excellent reputation
        attestation_score=1.0,  # Fresh attestation
        history_score=0.8       # Good history
    )
    
    print(f"Trust Level: {result['trust_level']:.2f}")
    print(f"Components:")
    for component, data in result['components'].items():
        print(f"  {component}: {data['score']:.2f} × {data['weight']:.2f} = {data['weighted_value']:.2f}")
    
    trust_tax = calculator.calculate_trust_tax(result['trust_level'])
    print(f"Trust Tax: {trust_tax*100:.2f}%\n")
    
    # Example 2: Low trust scenario
    print("Example 2: Low Trust Scenario")
    result = calculator.calculate_trust(
        audit_score=0.5,      # Partial audit issues
        reputation_score=0.3,  # Poor reputation
        attestation_score=0.4,  # Old attestation
        history_score=0.2       # New relationship
    )
    
    print(f"Trust Level: {result['trust_level']:.2f}")
    print(f"Components:")
    for component, data in result['components'].items():
        print(f"  {component}: {data['score']:.2f} × {data['weight']:.2f} = {data['weighted_value']:.2f}")
    
    trust_tax = calculator.calculate_trust_tax(result['trust_level'])
    print(f"Trust Tax: {trust_tax*100:.2f}%\n")
    
    # Example 3: Using helper methods
    print("Example 3: Using Helper Methods")
    audit_score = calculator.calculate_audit_score(
        audit_hash_verified=True,
        signature_valid=True,
        certificate_valid=True,
        nonce_fresh=True
    )
    
    reputation_score = calculator.calculate_reputation_score(
        total_interactions=150,
        successful_interactions=140,
        failed_interactions=10,
        blacklisted=False
    )
    
    attestation_score = calculator.calculate_attestation_score(
        attestation_age_hours=2.5,
        expires_at=datetime.utcnow()
    )
    
    history_score = calculator.calculate_history_score(
        relationship_age_days=45,
        total_interactions=150
    )
    
    result = calculator.calculate_trust(
        audit_score=audit_score,
        reputation_score=reputation_score,
        attestation_score=attestation_score,
        history_score=history_score
    )
    
    print(f"Trust Level: {result['trust_level']:.2f}")
    trust_tax = calculator.calculate_trust_tax(result['trust_level'])
    print(f"Trust Tax: {trust_tax*100:.2f}%")
    
    # Statistics
    stats = calculator.get_statistics()
    print(f"\nCalculator Statistics:")
    print(f"  Calculations: {stats['calculations_performed']}")
    print(f"  Average Trust: {stats['avg_trust_level']:.2f}")
