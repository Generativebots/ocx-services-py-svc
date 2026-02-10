"""
Authority Discovery Scanner - AI-powered document parser
Detects authority gaps in business documents
"""

import os
import json
import hashlib
from typing import List, Dict, Any
from datetime import datetime
import anthropic
from google.cloud import storage
import psycopg2
from psycopg2.extras import Json
import logging
logger = logging.getLogger(__name__)


class AuthorityGapScanner:
    """Scans business documents for authority fragmentation"""
    
    def __init__(self, db_url: str, anthropic_api_key: str) -> None:
        self.db_url = db_url
        self.client = anthropic.Anthropic(api_key=anthropic_api_key)
        self.conn = psycopg2.connect(db_url)
    
    def scan_document(self, company_id: str, doc_type: str, file_path: str, file_content: str) -> Dict[str, Any]:
        """
        Scan a single document for authority gaps
        
        Args:
            company_id: Company identifier
            doc_type: Type of document (BPMN, SOP, RACI, etc.)
            file_path: Path to the document
            file_content: Content of the document
        
        Returns:
            Scan results with detected gaps
        """
        # Parse document with Claude
        parsed_entities = self._parse_document(doc_type, file_content)
        
        # Detect authority gaps
        gaps = self._detect_gaps(parsed_entities)
        
        # Store parsed document
        doc_id = self._store_parsed_document(
            company_id, doc_type, file_path, len(file_content), 
            parsed_entities, len(gaps)
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
    
    def _parse_document(self, doc_type: str, content: str) -> Dict[str, Any]:
        """Use Claude to parse document and extract entities"""
        
        prompt = f"""Analyze this {doc_type} document and extract:

1. Decision points (what decisions are being made)
2. Authority holders (who has authority to decide)
3. Execution systems (what systems execute the decisions)
4. Accountability (who is blamed if things go wrong)
5. Override patterns (when discretion is used)
6. Time sensitivity (how urgent are decisions)

Document:
{content}

Return a JSON object with these fields:
{{
  "decision_points": [
    {{
      "description": "...",
      "reversible": true/false,
      "authority_holder": "...",
      "execution_system": "...",
      "accountability": "...",
      "override_frequency": "...",
      "time_sensitivity": "seconds|minutes|hours|days"
    }}
  ],
  "roles": [...],
  "systems": [...],
  "approval_flows": [...]
}}
"""
        
        message = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Extract JSON from response
        response_text = message.content[0].text
        
        # Find JSON in response
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        json_str = response_text[start:end]
        
        return json.loads(json_str)
    
    def _detect_gaps(self, entities: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect authority gaps from parsed entities"""
        gaps = []
        
        for decision in entities.get('decision_points', []):
            # Check for authority fragmentation
            if self._has_multi_approver(decision):
                gaps.append({
                    'type': 'Authority Fragmented',
                    'severity': 'HIGH',
                    'pattern': 'Multi-approver decision',
                    'decision_point': decision['description'],
                    'current_authority_holder': decision.get('authority_holder'),
                    'execution_system': decision.get('execution_system'),
                    'accountability_gap': decision.get('accountability'),
                    'override_frequency': self._parse_frequency(decision.get('override_frequency', '0')),
                    'time_sensitivity': decision.get('time_sensitivity', 'hours')
                })
            
            # Check for accountability ambiguity
            if self._has_accountability_gap(decision):
                gaps.append({
                    'type': 'Accountability Ambiguous',
                    'severity': 'MEDIUM',
                    'pattern': 'Authority holder ≠ Accountable party',
                    'decision_point': decision['description'],
                    'current_authority_holder': decision.get('authority_holder'),
                    'execution_system': decision.get('execution_system'),
                    'accountability_gap': decision.get('accountability'),
                    'override_frequency': self._parse_frequency(decision.get('override_frequency', '0')),
                    'time_sensitivity': decision.get('time_sensitivity', 'hours')
                })
            
            # Check for execution decoupling
            if self._has_execution_decoupling(decision):
                gaps.append({
                    'type': 'Execution Decoupled',
                    'severity': 'HIGH',
                    'pattern': 'Authority holder ≠ Executor',
                    'decision_point': decision['description'],
                    'current_authority_holder': decision.get('authority_holder'),
                    'execution_system': decision.get('execution_system'),
                    'accountability_gap': decision.get('accountability'),
                    'override_frequency': self._parse_frequency(decision.get('override_frequency', '0')),
                    'time_sensitivity': decision.get('time_sensitivity', 'hours')
                })
        
        return gaps
    
    def _has_multi_approver(self, decision: Dict) -> bool:
        """Check if decision has multiple approvers"""
        authority = decision.get('authority_holder', '')
        return 'and' in authority.lower() or ',' in authority or 'multiple' in authority.lower()
    
    def _has_accountability_gap(self, decision: Dict) -> bool:
        """Check if authority holder ≠ accountable party"""
        authority = decision.get('authority_holder', '').lower()
        accountability = decision.get('accountability', '').lower()
        return authority != accountability and len(accountability) > 0
    
    def _has_execution_decoupling(self, decision: Dict) -> bool:
        """Check if authority holder ≠ executor"""
        authority = decision.get('authority_holder', '').lower()
        executor = decision.get('execution_system', '').lower()
        return 'system' in executor or 'automated' in executor
    
    def _parse_frequency(self, freq_str: str) -> int:
        """Parse override frequency string to number per month"""
        freq_str = freq_str.lower()
        if 'daily' in freq_str or 'day' in freq_str:
            return 30
        elif 'weekly' in freq_str or 'week' in freq_str:
            return 4
        elif 'monthly' in freq_str or 'month' in freq_str:
            return 1
        elif 'rarely' in freq_str:
            return 0
        else:
            try:
                return int(''.join(filter(str.isdigit, freq_str)))
            except (ValueError, TypeError):
                return 0
    
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
            company_id, doc_type, os.path.basename(file_path), file_path,
            file_size, Json(entities), gaps_found
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

    def get_gap_by_id(self, gap_id: str) -> Dict[str, Any]:
        """Get a specific authority gap by ID"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT gap_id, gap_type, severity, decision_point,
                   current_authority_holder, execution_system,
                   accountability_gap, override_frequency,
                   time_sensitivity, a2a_candidacy_score, status
            FROM authority_gaps
            WHERE gap_id = %s
        """, (gap_id,))
        
        row = cursor.fetchone()
        cursor.close()
        
        if not row:
            return None
        
        return {
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
        }

    def update_gap_status(self, gap_id: str, new_status: str) -> bool:
        """Update the status of an authority gap"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE authority_gaps
            SET status = %s, updated_at = NOW()
            WHERE gap_id = %s
            RETURNING gap_id
        """, (new_status, gap_id))
        
        updated = cursor.fetchone() is not None
        self.conn.commit()
        cursor.close()
        return updated



# Example usage
if __name__ == '__main__':
    scanner = AuthorityGapScanner(
        db_url=os.getenv('DATABASE_URL'),
        anthropic_api_key=os.getenv('ANTHROPIC_API_KEY')
    )
    
    # Scan a sample SOP document
    with open('sample_sop.txt', 'r') as f:
        content = f.read()
    
    result = scanner.scan_document(
        company_id='company-123',
        doc_type='SOP',
        file_path='sample_sop.txt',
        file_content=content
    )
    
    print(f"Found {result['gaps_found']} authority gaps")
    for gap in result['gaps']:
        print(f"- {gap['type']}: {gap['decision_point']}")
