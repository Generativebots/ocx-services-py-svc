"""
A2A Use Case Generator - Creates use cases from authority gaps
Implements 5 canonical A2A patterns
"""

from typing import Dict, List, Any
from enum import Enum
import uuid
import logging
logger = logging.getLogger(__name__)


class A2APattern(Enum):
    ARBITRATION = "Arbitration"
    ESCALATION = "Escalation"
    VERIFICATION = "Verification"
    ENFORCEMENT = "Enforcement"
    RECOVERY = "Recovery"

class A2AUseCaseGenerator:
    """Generates A2A use cases from authority gaps"""
    
    def __init__(self, db_conn) -> None:
        self.conn = db_conn
    
    def generate_use_case(self, gap_id: str, canvas: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate an A2A use case from an authority gap and canvas
        
        Args:
            gap_id: Authority gap identifier
            canvas: Authority Discovery Canvas data
        
        Returns:
            Generated A2A use case
        """
        # Determine pattern type
        pattern = self._determine_pattern(canvas)
        
        # Generate use case based on pattern
        if pattern == A2APattern.ARBITRATION:
            use_case = self._generate_arbitration(gap_id, canvas)
        elif pattern == A2APattern.ESCALATION:
            use_case = self._generate_escalation(gap_id, canvas)
        elif pattern == A2APattern.VERIFICATION:
            use_case = self._generate_verification(gap_id, canvas)
        elif pattern == A2APattern.ENFORCEMENT:
            use_case = self._generate_enforcement(gap_id, canvas)
        else:  # RECOVERY
            use_case = self._generate_recovery(gap_id, canvas)
        
        # Store use case
        use_case_id = self._store_use_case(use_case)
        use_case['use_case_id'] = use_case_id
        
        return use_case
    
    def _determine_pattern(self, canvas: Dict[str, Any]) -> A2APattern:
        """Determine which A2A pattern applies"""
        
        # Check for arbitration (multiple decision makers)
        if 'and' in canvas.get('currentAuthorityHolder', {}).get('name', '').lower():
            return A2APattern.ARBITRATION
        
        # Check for escalation (human approval needed)
        if canvas.get('overrideFrequency', 0) > 5:
            return A2APattern.ESCALATION
        
        # Check for verification (accountability ≠ authority)
        if not canvas.get('accountabilityGap', {}).get('isAuthorityHolder', True):
            return A2APattern.VERIFICATION
        
        # Check for enforcement (system execution)
        if 'system' in canvas.get('executionSystem', '').lower():
            return A2APattern.ENFORCEMENT
        
        # Default to recovery
        return A2APattern.RECOVERY
    
    def _generate_arbitration(self, gap_id: str, canvas: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Arbitration A2A use case"""
        decision = canvas['decisionPoint']['description']
        authority = canvas['currentAuthorityHolder']['name']
        
        return {
            'gap_id': gap_id,
            'pattern_type': A2APattern.ARBITRATION.value,
            'title': f'Arbitration: {decision}',
            'description': f'Two agents disagree on {decision.lower()}, OCX arbitrates',
            'agents_involved': [
                {'name': f'{authority} Agent 1', 'role': 'Proposer', 'type': 'agent'},
                {'name': f'{authority} Agent 2', 'role': 'Validator', 'type': 'agent'},
                {'name': 'Jury', 'role': 'Arbitrator', 'type': 'ocx'}
            ],
            'current_problem': f'Multiple parties ({authority}) must agree on {decision.lower()}, leading to delays and conflicts',
            'ocx_proposal': f'Agent 1 proposes decision, Agent 2 validates. If disagreement, Jury arbitrates with binding verdict.',
            'authority_contract': self._generate_arbitration_contract(canvas)
        }
    
    def _generate_escalation(self, gap_id: str, canvas: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Escalation A2A use case"""
        decision = canvas['decisionPoint']['description']
        authority = canvas['currentAuthorityHolder']['name']
        
        return {
            'gap_id': gap_id,
            'pattern_type': A2APattern.ESCALATION.value,
            'title': f'Escalation: {decision}',
            'description': f'Agent executes {decision.lower()}, escalates to human when needed',
            'agents_involved': [
                {'name': 'Execution Agent', 'role': 'Executor', 'type': 'agent'},
                {'name': authority, 'role': 'Approver', 'type': 'human'},
                {'name': 'Escrow Gate', 'role': 'Barrier', 'type': 'ocx'}
            ],
            'current_problem': f'All {decision.lower()} require human approval, even routine ones',
            'ocx_proposal': f'Agent executes routine decisions automatically. Complex cases escalate to {authority} via Escrow Gate.',
            'authority_contract': self._generate_escalation_contract(canvas)
        }
    
    def _generate_verification(self, gap_id: str, canvas: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Verification A2A use case"""
        decision = canvas['decisionPoint']['description']
        executor = canvas['executionSystem']
        accountable = canvas['accountabilityGap']['blamedParty']
        
        return {
            'gap_id': gap_id,
            'pattern_type': A2APattern.VERIFICATION.value,
            'title': f'Verification: {decision}',
            'description': f'Execution agent acts, audit agent verifies compliance',
            'agents_involved': [
                {'name': f'{executor} Agent', 'role': 'Executor', 'type': 'agent'},
                {'name': 'Audit Agent', 'role': 'Verifier', 'type': 'agent'},
                {'name': accountable, 'role': 'Accountable', 'type': 'human'}
            ],
            'current_problem': f'{executor} executes {decision.lower()}, but {accountable} is blamed if it fails',
            'ocx_proposal': f'{executor} Agent executes immediately. Audit Agent verifies within 1 hour. Can revert if non-compliant.',
            'authority_contract': self._generate_verification_contract(canvas)
        }
    
    def _generate_enforcement(self, gap_id: str, canvas: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Enforcement A2A use case"""
        decision = canvas['decisionPoint']['description']
        
        return {
            'gap_id': gap_id,
            'pattern_type': A2APattern.ENFORCEMENT.value,
            'title': f'Enforcement: {decision}',
            'description': f'Agent proposes {decision.lower()}, OCX enforces compliance',
            'agents_involved': [
                {'name': 'Proposal Agent', 'role': 'Proposer', 'type': 'agent'},
                {'name': 'Compliance Agent', 'role': 'Enforcer', 'type': 'agent'},
                {'name': 'Speculative Executor', 'role': 'Sandbox', 'type': 'ocx'}
            ],
            'current_problem': f'{decision} is proposed but compliance checks happen after execution',
            'ocx_proposal': f'Agent proposes in sandbox. Compliance Agent enforces rules. Auto-commit if compliant, revert if not.',
            'authority_contract': self._generate_enforcement_contract(canvas)
        }
    
    def _generate_recovery(self, gap_id: str, canvas: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Recovery A2A use case"""
        decision = canvas['decisionPoint']['description']
        
        return {
            'gap_id': gap_id,
            'pattern_type': A2APattern.RECOVERY.value,
            'title': f'Recovery: {decision}',
            'description': f'Primary agent fails, backup agent takes over',
            'agents_involved': [
                {'name': 'Primary Agent', 'role': 'Primary', 'type': 'agent'},
                {'name': 'Backup Agent', 'role': 'Backup', 'type': 'agent'},
                {'name': 'Health Monitor', 'role': 'Monitor', 'type': 'ocx'}
            ],
            'current_problem': f'If primary system fails during {decision.lower()}, process halts',
            'ocx_proposal': f'Primary Agent has authority. Health Monitor detects failure. Backup Agent takes over with state transfer.',
            'authority_contract': self._generate_recovery_contract(canvas)
        }
    
    def _generate_arbitration_contract(self, canvas: Dict[str, Any]) -> str:
        """Generate authority contract for Arbitration pattern"""
        return f"""If Agent 1 and Agent 2 disagree on {canvas['decisionPoint']['description']}, Jury arbitrates.
Both agents must comply with Jury verdict.
Timeout: 30 seconds for arbitration."""
    
    def _generate_escalation_contract(self, canvas: Dict[str, Any]) -> str:
        """Generate authority contract for Escalation pattern"""
        return f"""Agent executes {canvas['decisionPoint']['description']} automatically if routine.
If complex (override frequency > {canvas['overrideFrequency']}), escalate to {canvas['currentAuthorityHolder']['name']}.
Timeout: {canvas['timeSensitivity']} for human response."""
    
    def _generate_verification_contract(self, canvas: Dict[str, Any]) -> str:
        """Generate authority contract for Verification pattern"""
        return f"""{canvas['executionSystem']} Agent executes {canvas['decisionPoint']['description']} immediately.
Audit Agent verifies within 1 hour.
If non-compliant, Audit Agent can revert.
Accountable party: {canvas['accountabilityGap']['blamedParty']}"""
    
    def _generate_enforcement_contract(self, canvas: Dict[str, Any]) -> str:
        """Generate authority contract for Enforcement pattern"""
        return f"""Agent proposes {canvas['decisionPoint']['description']} in sandbox.
Compliance Agent enforces rules.
Auto-commit if compliant, revert if not.
Reversible: {canvas['decisionPoint']['reversible']}"""
    
    def _generate_recovery_contract(self, canvas: Dict[str, Any]) -> str:
        """Generate authority contract for Recovery pattern"""
        return f"""Primary Agent has authority for {canvas['decisionPoint']['description']}.
Health Monitor checks every 5 minutes.
If unavailable > 5 minutes, Backup Agent takes over.
State transfer via Redis snapshot."""
    
    def _store_use_case(self, use_case: Dict[str, Any]) -> str:
        """Store use case in database"""
        cursor = self.conn.cursor()
        
        use_case_id = str(uuid.uuid4())
        
        cursor.execute("""
            INSERT INTO a2a_use_cases 
            (use_case_id, company_id, gap_id, pattern_type, title, description,
             agents_involved, current_problem, ocx_proposal, authority_contract)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            use_case_id,
            'company-demo',  # TODO: Get from context
            use_case['gap_id'],
            use_case['pattern_type'],
            use_case['title'],
            use_case['description'],
            use_case['agents_involved'],
            use_case['current_problem'],
            use_case['ocx_proposal'],
            use_case['authority_contract']
        ))
        
        self.conn.commit()
        cursor.close()
        
        return use_case_id
    
    def get_use_cases(self, company_id: str, pattern_type: str = None) -> List[Dict[str, Any]]:
        """Get all A2A use cases for a company"""
        cursor = self.conn.cursor()
        
        if pattern_type:
            cursor.execute("""
                SELECT use_case_id, gap_id, pattern_type, title, description,
                       agents_involved, current_problem, ocx_proposal,
                       authority_contract, status
                FROM a2a_use_cases
                WHERE company_id = %s AND pattern_type = %s
                ORDER BY created_at DESC
            """, (company_id, pattern_type))
        else:
            cursor.execute("""
                SELECT use_case_id, gap_id, pattern_type, title, description,
                       agents_involved, current_problem, ocx_proposal,
                       authority_contract, status
                FROM a2a_use_cases
                WHERE company_id = %s
                ORDER BY created_at DESC
            """, (company_id,))
        
        use_cases = []
        for row in cursor.fetchall():
            use_cases.append({
                'use_case_id': str(row[0]),
                'gap_id': str(row[1]),
                'pattern_type': row[2],
                'title': row[3],
                'description': row[4],
                'agents_involved': row[5],
                'current_problem': row[6],
                'ocx_proposal': row[7],
                'authority_contract': row[8],
                'status': row[9]
            })
        
        cursor.close()
        return use_cases
