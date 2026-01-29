"""
Authority Contract Generator - Creates executable YAML contracts
"""

import yaml
from typing import Dict, Any
import uuid

class AuthorityContractGenerator:
    """Generates executable authority contracts from A2A use cases"""
    
    def __init__(self, db_conn):
        self.conn = db_conn
    
    def generate_contract(self, use_case_id: str) -> Dict[str, Any]:
        """Generate authority contract from use case"""
        # Fetch use case
        use_case = self._get_use_case(use_case_id)
        
        # Generate contract based on pattern
        if use_case['pattern_type'] == 'Arbitration':
            contract = self._generate_arbitration_contract(use_case)
        elif use_case['pattern_type'] == 'Escalation':
            contract = self._generate_escalation_contract(use_case)
        elif use_case['pattern_type'] == 'Verification':
            contract = self._generate_verification_contract(use_case)
        elif use_case['pattern_type'] == 'Enforcement':
            contract = self._generate_enforcement_contract(use_case)
        else:  # Recovery
            contract = self._generate_recovery_contract(use_case)
        
        # Store contract
        contract_id = self._store_contract(use_case_id, contract)
        contract['contract_id'] = contract_id
        
        return contract
    
    def _generate_arbitration_contract(self, use_case: Dict) -> Dict:
        agents = use_case['agents_involved']
        return {
            'contract_id': str(uuid.uuid4()),
            'pattern': 'Arbitration',
            'version': '1.0',
            'parties': [
                {'agent_id': agents[0]['name'].lower().replace(' ', '-'),
                 'role': 'Proposer',
                 'spiffe_id': f"spiffe://company.com/agent/{agents[0]['name'].lower().replace(' ', '-')}"},
                {'agent_id': agents[1]['name'].lower().replace(' ', '-'),
                 'role': 'Validator',
                 'spiffe_id': f"spiffe://company.com/agent/{agents[1]['name'].lower().replace(' ', '-')}"}
            ],
            'decision_point': {
                'description': use_case['title'],
                'trigger': 'agent_proposal'
            },
            'authority_rules': [
                {'if': 'validator.approve == true', 'then': 'execute(proposal)'},
                {'if': 'validator.approve == false', 'then': 'escalate_to_jury(proposal, objection)'},
                {'if': 'jury.verdict == APPROVE', 'then': 'execute(proposal)'},
                {'if': 'jury.verdict == REJECT', 'then': 'revert(proposal)'}
            ],
            'enforcement': {
                'method': 'speculative_execution',
                'timeout': '30s',
                'revert_on_failure': True
            },
            'audit': {
                'ledger': 'trust_attestations',
                'retention': '7 years'
            }
        }
    
    def _generate_escalation_contract(self, use_case: Dict) -> Dict:
        return {
            'contract_id': str(uuid.uuid4()),
            'pattern': 'Escalation',
            'version': '1.0',
            'parties': [
                {'agent_id': 'execution-agent', 'role': 'Executor'},
                {'agent_id': 'human-approver', 'role': 'Approver'}
            ],
            'decision_point': {
                'description': use_case['title'],
                'trigger': 'threshold_exceeded'
            },
            'authority_rules': [
                {'if': 'amount <= threshold', 'then': 'execute_automatically()'},
                {'if': 'amount > threshold', 'then': 'escalate_to_human()'},
                {'if': 'human.approve == true', 'then': 'execute(proposal)'},
                {'if': 'human.approve == false', 'then': 'reject(proposal)'}
            ],
            'enforcement': {
                'method': 'escrow_gate',
                'timeout': '5m',
                'revert_on_timeout': True
            },
            'audit': {
                'ledger': 'trust_attestations',
                'retention': '7 years'
            }
        }
    
    def _generate_verification_contract(self, use_case: Dict) -> Dict:
        return {
            'contract_id': str(uuid.uuid4()),
            'pattern': 'Verification',
            'version': '1.0',
            'parties': [
                {'agent_id': 'execution-agent', 'role': 'Executor'},
                {'agent_id': 'audit-agent', 'role': 'Verifier'}
            ],
            'decision_point': {
                'description': use_case['title'],
                'trigger': 'execution_complete'
            },
            'authority_rules': [
                {'if': 'execution_complete', 'then': 'notify_audit_agent()'},
                {'if': 'audit.pass == true', 'then': 'commit()'},
                {'if': 'audit.pass == false', 'then': 'revert()'},
                {'if': 'audit_timeout', 'then': 'commit()'}  # Auto-commit after 1 hour
            ],
            'enforcement': {
                'method': 'parallel_execution',
                'audit_window': '1h',
                'revert_on_failure': True
            },
            'audit': {
                'ledger': 'trust_attestations',
                'retention': '7 years'
            }
        }
    
    def _generate_enforcement_contract(self, use_case: Dict) -> Dict:
        return {
            'contract_id': str(uuid.uuid4()),
            'pattern': 'Enforcement',
            'version': '1.0',
            'parties': [
                {'agent_id': 'proposal-agent', 'role': 'Proposer'},
                {'agent_id': 'compliance-agent', 'role': 'Enforcer'}
            ],
            'decision_point': {
                'description': use_case['title'],
                'trigger': 'agent_proposal'
            },
            'authority_rules': [
                {'if': 'proposal_submitted', 'then': 'execute_in_sandbox()'},
                {'if': 'compliance.pass == true', 'then': 'commit()'},
                {'if': 'compliance.pass == false', 'then': 'revert()'}
            ],
            'enforcement': {
                'method': 'speculative_execution',
                'timeout': '30s',
                'revert_on_failure': True
            },
            'audit': {
                'ledger': 'trust_attestations',
                'retention': '7 years'
            }
        }
    
    def _generate_recovery_contract(self, use_case: Dict) -> Dict:
        return {
            'contract_id': str(uuid.uuid4()),
            'pattern': 'Recovery',
            'version': '1.0',
            'parties': [
                {'agent_id': 'primary-agent', 'role': 'Primary'},
                {'agent_id': 'backup-agent', 'role': 'Backup'}
            ],
            'decision_point': {
                'description': use_case['title'],
                'trigger': 'health_check_failure'
            },
            'authority_rules': [
                {'if': 'primary.healthy == true', 'then': 'use_primary()'},
                {'if': 'primary.unavailable > 5m', 'then': 'failover_to_backup()'},
                {'if': 'backup.active', 'then': 'transfer_state()'}
            ],
            'enforcement': {
                'method': 'health_monitor',
                'check_interval': '1m',
                'failover_timeout': '5m'
            },
            'audit': {
                'ledger': 'trust_attestations',
                'retention': '7 years'
            }
        }
    
    def _get_use_case(self, use_case_id: str) -> Dict:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT pattern_type, title, agents_involved
            FROM a2a_use_cases
            WHERE use_case_id = %s
        """, (use_case_id,))
        row = cursor.fetchone()
        cursor.close()
        return {
            'pattern_type': row[0],
            'title': row[1],
            'agents_involved': row[2]
        }
    
    def _store_contract(self, use_case_id: str, contract: Dict) -> str:
        cursor = self.conn.cursor()
        contract_id = str(uuid.uuid4())
        contract_yaml = yaml.dump(contract, default_flow_style=False)
        
        cursor.execute("""
            INSERT INTO authority_contracts 
            (contract_id, use_case_id, company_id, contract_yaml,
             contract_version, agents, decision_point, authority_rules,
             enforcement, audit_config)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            contract_id, use_case_id, 'company-demo',
            contract_yaml, contract['version'],
            contract['parties'], contract['decision_point'],
            contract['authority_rules'], contract['enforcement'],
            contract['audit']
        ))
        
        self.conn.commit()
        cursor.close()
        return contract_id
