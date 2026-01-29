"""
Mock Scanner for Demo - No Claude API required
Returns pre-defined authority gaps based on document type
"""

import uuid
from typing import Dict, List, Any
from datetime import datetime

class MockScanner:
    """Mock scanner that returns pre-defined gaps for demo scenarios"""
    
    def __init__(self, db_conn):
        self.conn = db_conn
        self.scenarios = self._load_scenarios()
    
    def _load_scenarios(self) -> Dict[str, List[Dict]]:
        """Load pre-defined demo scenarios"""
        return {
            'purchase_order_sop.txt': [
                {
                    'type': 'Authority Fragmented',
                    'severity': 'HIGH',
                    'pattern': 'Multi-approver decision',
                    'decision_point': 'Purchase order approval over $10,000',
                    'current_authority_holder': 'Finance Manager and Procurement Manager',
                    'execution_system': 'SAP',
                    'accountability_gap': 'Operations Director',
                    'override_frequency': 15,
                    'time_sensitivity': 'hours'
                },
                {
                    'type': 'Accountability Ambiguous',
                    'severity': 'MEDIUM',
                    'pattern': 'Authority holder ≠ Accountable party',
                    'decision_point': 'Vendor selection for critical supplies',
                    'current_authority_holder': 'Procurement Manager',
                    'execution_system': 'SAP',
                    'accountability_gap': 'Operations Director',
                    'override_frequency': 8,
                    'time_sensitivity': 'days'
                },
                {
                    'type': 'Execution Decoupled',
                    'severity': 'HIGH',
                    'pattern': 'Authority holder ≠ Executor',
                    'decision_point': 'Order execution after approval',
                    'current_authority_holder': 'Finance Manager',
                    'execution_system': 'SAP Automated System',
                    'accountability_gap': 'Finance Manager',
                    'override_frequency': 0,
                    'time_sensitivity': 'minutes'
                }
            ],
            'patient_transfer_protocol.txt': [
                {
                    'type': 'Accountability Ambiguous',
                    'severity': 'HIGH',
                    'pattern': 'Authority holder ≠ Accountable party',
                    'decision_point': 'Patient transfer between facilities',
                    'current_authority_holder': 'Transfer Coordinator',
                    'execution_system': 'EMR System',
                    'accountability_gap': 'Medical Director',
                    'override_frequency': 12,
                    'time_sensitivity': 'minutes'
                },
                {
                    'type': 'Execution Decoupled',
                    'severity': 'HIGH',
                    'pattern': 'Authority holder ≠ Executor',
                    'decision_point': 'Compliance verification post-transfer',
                    'current_authority_holder': 'Compliance Officer',
                    'execution_system': 'Automated Audit System',
                    'accountability_gap': 'Medical Director',
                    'override_frequency': 5,
                    'time_sensitivity': 'hours'
                }
            ],
            'loan_approval_workflow.txt': [
                {
                    'type': 'Authority Fragmented',
                    'severity': 'HIGH',
                    'pattern': 'Multi-level approval',
                    'decision_point': 'Loan approval over $50,000',
                    'current_authority_holder': 'Loan Officer and Senior Loan Officer',
                    'execution_system': 'Loan Management System',
                    'accountability_gap': 'Branch Manager',
                    'override_frequency': 20,
                    'time_sensitivity': 'hours'
                },
                {
                    'type': 'Execution Decoupled',
                    'severity': 'MEDIUM',
                    'pattern': 'Authority holder ≠ Executor',
                    'decision_point': 'Loan disbursement',
                    'current_authority_holder': 'Senior Loan Officer',
                    'execution_system': 'Automated Disbursement System',
                    'accountability_gap': 'Senior Loan Officer',
                    'override_frequency': 0,
                    'time_sensitivity': 'seconds'
                }
            ]
        }
    
    def scan_document(self, company_id: str, doc_type: str, file_path: str, file_content: str) -> Dict[str, Any]:
        """
        Mock scan that returns pre-defined gaps
        
        Args:
            company_id: Company identifier
            doc_type: Type of document
            file_path: Path to document
            file_content: Content (ignored in mock)
        
        Returns:
            Scan results with pre-defined gaps
        """
        # Get gaps for this file
        file_name = file_path.split('/')[-1] if '/' in file_path else file_path
        gaps = self.scenarios.get(file_name, [])
        
        # Store parsed document
        doc_id = self._store_parsed_document(
            company_id, doc_type, file_path, len(file_content), 
            {'mock': True, 'file_name': file_name}, len(gaps)
        )
        
        # Store gaps
        gap_ids = []
        for gap in gaps:
            gap_id = self._store_authority_gap(company_id, doc_id, file_path, gap)
            gap_ids.append(gap_id)
        
        return {
            'doc_id': doc_id,
            'gaps_found': len(gaps),
            'gap_ids': gap_ids,
            'gaps': gaps
        }
    
    def _store_parsed_document(self, company_id: str, doc_type: str, file_path: str, 
                                file_size: int, entities: Dict, gaps_found: int) -> str:
        """Store parsed document in database"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO parsed_documents 
            (company_id, doc_type, file_name, file_path, file_size, parsed_entities, gaps_found)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING doc_id
        """, (
            company_id, doc_type, file_path.split('/')[-1], file_path,
            file_size, entities, gaps_found
        ))
        
        doc_id = cursor.fetchone()[0]
        self.conn.commit()
        cursor.close()
        
        return str(doc_id)
    
    def _store_authority_gap(self, company_id: str, doc_id: str, doc_source: str, 
                             gap: Dict[str, Any]) -> str:
        """Store authority gap in database"""
        cursor = self.conn.cursor()
        
        # Calculate A2A candidacy score
        candidacy_score = self._calculate_candidacy_score(gap)
        
        cursor.execute("""
            INSERT INTO authority_gaps 
            (company_id, document_source, gap_type, severity, decision_point,
             current_authority_holder, execution_system, accountability_gap,
             override_frequency, time_sensitivity, a2a_candidacy_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING gap_id
        """, (
            company_id, doc_source, gap['type'], gap['severity'],
            gap['decision_point'], gap.get('current_authority_holder'),
            gap.get('execution_system'), gap.get('accountability_gap'),
            gap.get('override_frequency', 0), gap.get('time_sensitivity'),
            candidacy_score
        ))
        
        gap_id = cursor.fetchone()[0]
        self.conn.commit()
        cursor.close()
        
        return str(gap_id)
    
    def _calculate_candidacy_score(self, gap: Dict[str, Any]) -> float:
        """Calculate A2A candidacy score (0.0 - 1.0)"""
        score = 0.0
        
        # High severity = higher score
        if gap['severity'] == 'HIGH':
            score += 0.4
        elif gap['severity'] == 'MEDIUM':
            score += 0.2
        
        # Frequent overrides = higher score
        freq = gap.get('override_frequency', 0)
        if freq > 10:
            score += 0.3
        elif freq > 5:
            score += 0.2
        elif freq > 0:
            score += 0.1
        
        # Time-sensitive = higher score
        time_sens = gap.get('time_sensitivity', 'hours')
        if time_sens == 'seconds':
            score += 0.3
        elif time_sens == 'minutes':
            score += 0.2
        elif time_sens == 'hours':
            score += 0.1
        
        return min(1.0, score)
    
    def get_gaps(self, company_id: str, status: str = None) -> List[Dict[str, Any]]:
        """Get all authority gaps for a company"""
        cursor = self.conn.cursor()
        
        if status:
            cursor.execute("""
                SELECT gap_id, gap_type, severity, decision_point,
                       current_authority_holder, execution_system,
                       accountability_gap, override_frequency,
                       time_sensitivity, a2a_candidacy_score, status
                FROM authority_gaps
                WHERE company_id = %s AND status = %s
                ORDER BY a2a_candidacy_score DESC, created_at DESC
            """, (company_id, status))
        else:
            cursor.execute("""
                SELECT gap_id, gap_type, severity, decision_point,
                       current_authority_holder, execution_system,
                       accountability_gap, override_frequency,
                       time_sensitivity, a2a_candidacy_score, status
                FROM authority_gaps
                WHERE company_id = %s
                ORDER BY a2a_candidacy_score DESC, created_at DESC
            """, (company_id,))
        
        gaps = []
        for row in cursor.fetchall():
            gaps.append({
                'gap_id': str(row[0]),
                'gap_type': row[1],
                'severity': row[2],
                'decision_point': row[3],
                'current_authority_holder': row[4],
                'execution_system': row[5],
                'accountability_gap': row[6],
                'override_frequency': row[7],
                'time_sensitivity': row[8],
                'a2a_candidacy_score': float(row[9]),
                'status': row[10]
            })
        
        cursor.close()
        return gaps
