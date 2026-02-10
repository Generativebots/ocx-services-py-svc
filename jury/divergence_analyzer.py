"""
Divergence Analyzer - Additive Compliance Layer (Phase 2)

Analyzes where agent's speculative path diverged from policy expectations.
Does NOT modify core OCX enforcement - only provides analysis for human review.
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class DivergenceAnalyzer:
    """
    Analyze divergence between agent's ghost-state path and policy expectations.
    
    This is purely for human-in-the-loop oversight - it does not change
    OCX's core enforcement decisions.
    """
    
    def __init__(self, ghost_pool=None, ape_engine=None) -> None:
        """
        Initialize divergence analyzer.
        
        Args:
            ghost_pool: GhostPool instance (optional)
            ape_engine: APE Engine instance (optional)
        """
        self.ghost_pool = ghost_pool
        self.ape_engine = ape_engine
        logger.info("Divergence Analyzer initialized (additive layer)")
    
    def analyze_divergence(self, transaction_id: str) -> Dict:
        """
        Analyze where agent diverged from policy expectations.
        
        This is called AFTER OCX enforcement to help humans understand
        what happened. It does not affect the enforcement decision.
        
        Args:
            transaction_id: Transaction ID to analyze
        
        Returns:
            Dict: Divergence analysis
                {
                    'transaction_id': str,
                    'divergences': List[Dict],
                    'ghost_path': List[Dict],
                    'policies': List[Dict]
                }
        """
        # Get ghost-state path (from OCX core - read-only)
        ghost_path = self._get_ghost_path(transaction_id)
        
        # Get applicable policies (from APE Engine - read-only)
        policies = self._get_applicable_policies(transaction_id)
        
        # Find divergence points
        divergences = []
        for step_idx, step in enumerate(ghost_path):
            for policy in policies:
                # Check if policy was violated at this step
                violation = self._check_violation(step, policy)
                if violation:
                    divergences.append({
                        'step': step_idx + 1,
                        'policy_id': policy['policy_id'],
                        'policy_tier': policy.get('tier', 'UNKNOWN'),
                        'expected_action': policy.get('expected_action', 'BLOCK'),
                        'actual_action': step.get('action'),
                        'reason': violation['reason'],
                        'severity': violation.get('severity', 'MEDIUM')
                    })
        
        logger.info(f"Analyzed divergence for {transaction_id}: {len(divergences)} violations found")
        
        return {
            'transaction_id': transaction_id,
            'divergences': divergences,
            'ghost_path': ghost_path,
            'policies': policies,
            'summary': {
                'total_steps': len(ghost_path),
                'total_violations': len(divergences),
                'highest_severity': self._get_highest_severity(divergences)
            }
        }
    
    def _get_ghost_path(self, transaction_id: str) -> List[Dict]:
        """
        Get ghost-state path from OCX core (read-only).
        
        In production, this would query the GhostPool.
        For now, return dummy data.
        """
        # Dummy ghost path
        return [
            {
                'step': 1,
                'action': 'verify_identity',
                'state': {'agent_id': 'PROCUREMENT_BOT', 'pid_verified': True}
            },
            {
                'step': 2,
                'action': 'check_policy',
                'state': {'policy_version': 'v1.2.3', 'policy_result': 'PASS'}
            },
            {
                'step': 3,
                'action': 'execute_payment',
                'state': {'amount': 1500, 'vendor': 'ACME'}
            }
        ]
    
    def _get_applicable_policies(self, transaction_id: str) -> List[Dict]:
        """
        Get applicable policies from APE Engine (read-only).
        
        In production, this would query the APE Engine.
        For now, return dummy data.
        """
        # Dummy policies
        return [
            {
                'policy_id': 'PROCUREMENT_001',
                'tier': 'GLOBAL',
                'logic': {'>': [{'var': 'amount'}, 500]},
                'expected_action': 'BLOCK',
                'threshold': 500
            },
            {
                'policy_id': 'SECURITY_001',
                'tier': 'GLOBAL',
                'logic': {'>': [{'var': 'entropy'}, 4.0]},
                'expected_action': 'BLOCK',
                'threshold': 4.0
            }
        ]
    
    def _check_violation(self, step: Dict, policy: Dict) -> Optional[Dict]:
        """
        Check if a step violated a policy.
        
        Args:
            step: Ghost-state step
            policy: Policy definition
        
        Returns:
            Dict: Violation details or None
        """
        # Simple threshold check (in production, use JSON-Logic evaluation)
        if step['action'] == 'execute_payment':
            amount = step['state'].get('amount', 0)
            threshold = policy.get('threshold', 0)
            
            if policy['policy_id'] == 'PROCUREMENT_001' and amount > threshold:
                return {
                    'reason': f"Amount ${amount} exceeds threshold ${threshold}",
                    'severity': 'HIGH' if amount > threshold * 2 else 'MEDIUM'
                }
        
        return None
    
    def _get_highest_severity(self, divergences: List[Dict]) -> str:
        """Get highest severity from divergences."""
        if not divergences:
            return 'NONE'
        
        severities = [d.get('severity', 'MEDIUM') for d in divergences]
        if 'HIGH' in severities:
            return 'HIGH'
        elif 'MEDIUM' in severities:
            return 'MEDIUM'
        else:
            return 'LOW'


# Example usage (does not modify core OCX)
if __name__ == "__main__":
    analyzer = DivergenceAnalyzer()
    
    # Analyze a transaction (read-only operation)
    result = analyzer.analyze_divergence('tx-12345')
    
    print(f"Transaction: {result['transaction_id']}")
    print(f"Total violations: {result['summary']['total_violations']}")
    print(f"Highest severity: {result['summary']['highest_severity']}")
    
    for div in result['divergences']:
        print(f"\nStep {div['step']}: {div['policy_id']}")
        print(f"  Reason: {div['reason']}")
        print(f"  Severity: {div['severity']}")
