"""
Slack Shadow-SOP Observer - Additive Compliance Layer (Phase 3)

Passively observes Slack messages to discover undocumented tribal knowledge.
Does NOT modify core OCX enforcement - only discovers new policies for human review.
"""

from typing import Dict, List, Optional
import logging
import re

logger = logging.getLogger(__name__)


class SlackShadowSOPObserver:
    """
    Passive observer for Slack channels to discover tribal knowledge.
    
    This discovers informal rules that humans use but aren't in official SOPs.
    Discovered rules require human approval before becoming official policies.
    """
    
    def __init__(self, bot_token: str = None, app_token: str = None, llm_client=None):
        """
        Initialize Slack observer.
        
        Args:
            bot_token: Slack bot token (optional for testing)
            app_token: Slack app token (optional for testing)
            llm_client: LLM client for extraction (optional)
        """
        self.bot_token = bot_token
        self.app_token = app_token
        self.llm = llm_client
        self.discovered_sops = []
        
        # Pattern detection for tribal knowledge
        self.patterns = [
            r"we always\s+(.+)",
            r"never\s+(.+)\s+without\s+(.+)",
            r"the rule is\s+(.+)",
            r"make sure to\s+(.+)",
            r"don't forget to\s+(.+)",
            r"remember to\s+(.+)",
            r"from now on,?\s+(.+)",
            r"going forward,?\s+(.+)"
        ]
        
        logger.info("Slack Shadow-SOP Observer initialized (additive layer)")
    
    def listen_for_tribal_knowledge(self):
        """
        Start listening to Slack channels for tribal knowledge.
        
        This is a passive observer - it does not affect OCX enforcement.
        Discovered rules go to human review queue.
        """
        # In production, this would use Slack SDK Socket Mode
        # For now, simulate with dummy data
        logger.info("Listening for tribal knowledge in Slack...")
        
        # Simulate processing messages
        dummy_messages = [
            "We always get CTO approval for cloud costs over $5k/month",
            "Never deploy on Fridays without QA sign-off",
            "The rule is to check with legal before any customer data export"
        ]
        
        for msg in dummy_messages:
            self.process_message(msg, channel='#engineering-leads', author='alice')
    
    def process_message(self, text: str, channel: str, author: str):
        """
        Process a Slack message for tribal knowledge.
        
        Args:
            text: Message text
            channel: Slack channel
            author: Message author
        """
        # Check if message matches tribal knowledge patterns
        for pattern in self.patterns:
            match = re.search(pattern, text.lower())
            if match:
                # Extract potential rule
                rule_text = match.group(1) if match.groups() else text
                
                # Use LLM to extract structured policy
                shadow_sop = self.extract_tribal_knowledge(text, channel, author)
                
                if shadow_sop and shadow_sop['confidence'] > 0.7:
                    self.store_shadow_sop(shadow_sop)
                    logger.info(f"Discovered shadow SOP: {shadow_sop['rule'][:50]}...")
    
    def extract_tribal_knowledge(self, text: str, channel: str, author: str) -> Optional[Dict]:
        """
        Extract structured policy from Slack message using LLM.
        
        Args:
            text: Message text
            channel: Slack channel
            author: Message author
        
        Returns:
            Dict: Shadow SOP or None
        """
        # In production, this would call vLLM/GPT
        # For now, use simple extraction
        
        # Dummy LLM extraction
        if "cloud costs" in text.lower():
            return {
                'rule': 'Get CTO approval for cloud costs over $5k/month',
                'confidence': 0.9,
                'category': 'procurement',
                'source': 'slack',
                'channel': channel,
                'author': author,
                'original_text': text,
                'suggested_logic': {
                    'and': [
                        {'>': [{'var': 'cloud_cost_monthly'}, 5000]},
                        {'not': {'in': [{'var': 'approver'}, ['CTO']]}}
                    ]
                },
                'suggested_action': 'BLOCK'
            }
        
        elif "deploy on fridays" in text.lower():
            return {
                'rule': 'Never deploy on Fridays without QA sign-off',
                'confidence': 0.85,
                'category': 'security',
                'source': 'slack',
                'channel': channel,
                'author': author,
                'original_text': text,
                'suggested_logic': {
                    'and': [
                        {'==': [{'var': 'day_of_week'}, 'Friday']},
                        {'not': {'in': [{'var': 'qa_approved'}, [True]]}}
                    ]
                },
                'suggested_action': 'BLOCK'
            }
        
        return None
    
    def store_shadow_sop(self, shadow_sop: Dict):
        """
        Store discovered shadow SOP for human review.
        
        Args:
            shadow_sop: Shadow SOP data
        """
        shadow_sop['status'] = 'pending'
        shadow_sop['discovered_at'] = __import__('datetime').datetime.utcnow().isoformat()
        
        self.discovered_sops.append(shadow_sop)
        
        # In production, store in Cloud Spanner shadow_sops table
        logger.info(f"Stored shadow SOP for review: {shadow_sop['rule'][:50]}...")
    
    def get_pending_reviews(self) -> List[Dict]:
        """
        Get shadow SOPs pending human review.
        
        Returns:
            List[Dict]: Pending shadow SOPs
        """
        return [sop for sop in self.discovered_sops if sop['status'] == 'pending']
    
    def approve_shadow_sop(self, sop_id: int, reviewed_by: str) -> Dict:
        """
        Approve shadow SOP and promote to official policy.
        
        This does NOT affect past OCX decisions - only adds new policy
        for future enforcement.
        
        Args:
            sop_id: Index of shadow SOP
            reviewed_by: Human reviewer
        
        Returns:
            Dict: Approval result
        """
        if sop_id >= len(self.discovered_sops):
            return {'success': False, 'error': 'Shadow SOP not found'}
        
        shadow_sop = self.discovered_sops[sop_id]
        shadow_sop['status'] = 'approved'
        shadow_sop['reviewed_by'] = reviewed_by
        shadow_sop['reviewed_at'] = __import__('datetime').datetime.utcnow().isoformat()
        
        # In production, this would:
        # 1. Add to APE Engine as official policy
        # 2. Update Go-Gateway for future enforcement
        # 3. Notify governance team
        
        logger.info(f"Approved shadow SOP: {shadow_sop['rule']}")
        
        return {
            'success': True,
            'shadow_sop': shadow_sop,
            'message': 'Shadow SOP promoted to official policy for future enforcement'
        }
    
    def reject_shadow_sop(self, sop_id: int, reviewed_by: str, reason: str) -> Dict:
        """
        Reject shadow SOP.
        
        Args:
            sop_id: Index of shadow SOP
            reviewed_by: Human reviewer
            reason: Rejection reason
        
        Returns:
            Dict: Rejection result
        """
        if sop_id >= len(self.discovered_sops):
            return {'success': False, 'error': 'Shadow SOP not found'}
        
        shadow_sop = self.discovered_sops[sop_id]
        shadow_sop['status'] = 'rejected'
        shadow_sop['reviewed_by'] = reviewed_by
        shadow_sop['rejection_reason'] = reason
        shadow_sop['reviewed_at'] = __import__('datetime').datetime.utcnow().isoformat()
        
        logger.info(f"Rejected shadow SOP: {shadow_sop['rule']}")
        
        return {
            'success': True,
            'shadow_sop': shadow_sop,
            'message': 'Shadow SOP rejected'
        }


# Example usage (does not modify core OCX)
if __name__ == "__main__":
    observer = SlackShadowSOPObserver()
    
    # Start listening (passive observation)
    observer.listen_for_tribal_knowledge()
    
    # Get pending reviews
    pending = observer.get_pending_reviews()
    print(f"Discovered {len(pending)} shadow SOPs for review:")
    
    for i, sop in enumerate(pending):
        print(f"\n{i+1}. {sop['rule']}")
        print(f"   Confidence: {sop['confidence']}")
        print(f"   Source: {sop['channel']} by {sop['author']}")
    
    # Human approves first shadow SOP
    if pending:
        result = observer.approve_shadow_sop(0, reviewed_by='human_governor_alice')
        print(f"\nApproval result: {result['message']}")
