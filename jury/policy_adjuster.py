"""
Policy Adjuster - Additive Compliance Layer (Phase 2)

Allows human governors to adjust policies based on divergence analysis.
Does NOT bypass core OCX enforcement - only updates policies for future enforcement.
"""

from typing import Dict, Optional
import logging
import json

logger = logging.getLogger(__name__)


class PolicyAdjuster:
    """
    Adjust policies based on human-in-the-loop decisions.
    
    This updates policies for FUTURE enforcement - it does not retroactively
    change OCX's core enforcement decisions.
    """
    
    def __init__(self, ape_engine=None, gateway_client=None):
        """
        Initialize policy adjuster.
        
        Args:
            ape_engine: APE Engine instance (optional)
            gateway_client: Go-Gateway client (optional)
        """
        self.ape_engine = ape_engine
        self.gateway = gateway_client
        self.adjustment_log = []
        logger.info("Policy Adjuster initialized (additive layer)")
    
    def adjust_policy(self, policy_id: str, adjustment: Dict) -> Dict:
        """
        Adjust a policy based on human decision.
        
        This updates the policy for FUTURE enforcement only.
        Past OCX decisions remain unchanged.
        
        Args:
            policy_id: Policy ID to adjust
            adjustment: Adjustment specification
                {
                    'type': 'increase_threshold' | 'add_exception' | 'change_action',
                    'new_value': Any,
                    'reason': str,
                    'approved_by': str
                }
        
        Returns:
            Dict: Adjustment result
        """
        # Get current policy (read-only from APE Engine)
        policy = self._get_policy(policy_id)
        if not policy:
            logger.error(f"Policy not found: {policy_id}")
            return {'success': False, 'error': 'Policy not found'}
        
        # Apply adjustment
        updated_policy = self._apply_adjustment(policy, adjustment)
        
        # Re-compile to JSON-Logic
        new_logic = self._compile_to_json_logic(updated_policy)
        
        # Update APE Engine (for future enforcement)
        if self.ape_engine:
            self.ape_engine.update_policy(policy_id, new_logic)
        
        # Update Go-Gateway Lua script (for future enforcement)
        if self.gateway:
            self._update_gateway_lua(policy_id, new_logic)
        
        # Log adjustment
        log_entry = {
            'policy_id': policy_id,
            'adjustment_type': adjustment['type'],
            'old_value': policy.get('threshold') or policy.get('action'),
            'new_value': adjustment.get('new_value'),
            'reason': adjustment.get('reason'),
            'approved_by': adjustment.get('approved_by'),
            'timestamp': __import__('datetime').datetime.utcnow().isoformat()
        }
        self.adjustment_log.append(log_entry)
        
        logger.info(f"Adjusted policy {policy_id}: {adjustment['type']}")
        
        return {
            'success': True,
            'policy_id': policy_id,
            'adjustment': log_entry,
            'updated_policy': updated_policy
        }
    
    def _get_policy(self, policy_id: str) -> Optional[Dict]:
        """Get policy from APE Engine (read-only)."""
        # Dummy policy for testing
        return {
            'policy_id': policy_id,
            'tier': 'GLOBAL',
            'logic': {'>': [{'var': 'amount'}, 500]},
            'action': {'on_fail': 'BLOCK', 'on_pass': 'ALLOW'},
            'threshold': 500
        }
    
    def _apply_adjustment(self, policy: Dict, adjustment: Dict) -> Dict:
        """
        Apply adjustment to policy.
        
        Args:
            policy: Current policy
            adjustment: Adjustment specification
        
        Returns:
            Dict: Updated policy
        """
        updated = policy.copy()
        
        if adjustment['type'] == 'increase_threshold':
            # Increase threshold by percentage or absolute value
            new_value = adjustment['new_value']
            updated['threshold'] = new_value
            updated['logic']['>'][1] = new_value
        
        elif adjustment['type'] == 'add_exception':
            # Add exception to policy logic
            exception = adjustment['exception']
            if 'exceptions' not in updated:
                updated['exceptions'] = []
            updated['exceptions'].append(exception)
        
        elif adjustment['type'] == 'change_action':
            # Change action (BLOCK -> WARN)
            new_action = adjustment['new_value']
            updated['action']['on_fail'] = new_action
        
        return updated
    
    def _compile_to_json_logic(self, policy: Dict) -> Dict:
        """
        Re-compile policy to JSON-Logic format.
        
        Args:
            policy: Updated policy
        
        Returns:
            Dict: JSON-Logic representation
        """
        # In production, this would use the APE Engine's compiler
        return policy['logic']
    
    def _update_gateway_lua(self, policy_id: str, new_logic: Dict):
        """
        Update Go-Gateway Lua script with new policy.
        
        This notifies the Gateway to reload policies for FUTURE requests.
        """
        # In production, this would call Gateway's reload endpoint
        logger.info(f"Notified Gateway to reload policy: {policy_id}")
    
    def get_adjustment_history(self, policy_id: Optional[str] = None) -> list:
        """
        Get adjustment history.
        
        Args:
            policy_id: Optional policy ID to filter
        
        Returns:
            List[Dict]: Adjustment log entries
        """
        if policy_id:
            return [log for log in self.adjustment_log if log['policy_id'] == policy_id]
        return self.adjustment_log


# Example usage (does not modify past OCX decisions)
if __name__ == "__main__":
    adjuster = PolicyAdjuster()
    
    # Human governor adjusts policy for FUTURE enforcement
    adjustment = {
        'type': 'increase_threshold',
        'new_value': 1000,
        'reason': 'Approved for trusted vendors based on divergence analysis',
        'approved_by': 'human_governor_alice'
    }
    
    result = adjuster.adjust_policy('PROCUREMENT_001', adjustment)
    
    if result['success']:
        print(f"Policy adjusted: {result['policy_id']}")
        print(f"New threshold: {result['updated_policy']['threshold']}")
        print(f"Reason: {result['adjustment']['reason']}")
    
    # View adjustment history
    history = adjuster.get_adjustment_history()
    print(f"\nTotal adjustments: {len(history)}")
