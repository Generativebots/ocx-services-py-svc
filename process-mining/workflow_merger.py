"""
Multi-Document Workflow Merger
Combines multiple related documents into a single comprehensive EBCL activity
"""

import os
from typing import Dict, List, Any
import json
from vertexai.generative_models import GenerativeModel
import vertexai

class WorkflowMerger:
    """Merge workflows from multiple documents into a single EBCL activity"""
    
    def __init__(self, project_id: str, location: str = "us-central1"):
        self.project_id = project_id
        self.location = location
        
        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel("gemini-1.5-pro-002")
    
    def merge_process_tables(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge process tables from multiple documents
        
        Args:
            documents: List of parsed documents with process_tables
        
        Returns:
            Merged process table
        """
        # Collect all process tables
        all_tables = []
        for doc in documents:
            all_tables.extend(doc.get('process_table', []))
        
        # Use Gemini to merge and deduplicate
        prompt = f"""
You are merging process tables from multiple related business documents.

Documents:
{json.dumps([{'type': d['document_type'], 'table': d['process_table']} for d in documents], indent=2)}

Tasks:
1. Merge all process steps into a single coherent workflow
2. Remove duplicates (same actor + action)
3. Resolve conflicts (if documents contradict, use this priority: Compliance > Policy > SOP > Email)
4. Maintain logical order (Request → Validation → Approval → Execution → Closure)
5. Normalize actor names consistently

Return a JSON array of merged process steps in logical order.

Example format:
[
  {{
    "actor": "Requester",
    "action": "Submit purchase request",
    "input": "Purchase need",
    "output": "Purchase request",
    "condition": null,
    "system": "ERP",
    "source_documents": ["SOP v3.2", "Policy v2.1"]
  }}
]

IMPORTANT:
- Preserve all unique steps
- Merge duplicate steps and track source documents
- Resolve conflicts using priority rules
- Maintain workflow order

Return JSON only, no explanation.
"""
        
        response = self.model.generate_content(prompt)
        
        try:
            merged_table = json.loads(response.text)
            return merged_table
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return all_tables  # Fallback to unmerged
    
    def resolve_conflicts(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Resolve conflicts between documents
        
        Priority: Compliance > Policy > SOP > Email
        """
        prompt = f"""
You are resolving conflicts between multiple business documents.

Documents:
{json.dumps([{
    'type': d['document_type'],
    'version': d.get('metadata', {}).get('version', 'unknown'),
    'authority': d.get('metadata', {}).get('owner', 'unknown'),
    'key_points': d.get('process_table', [])[:3]
} for d in documents], indent=2)}

Conflict Resolution Rules:
1. Compliance documents override everything
2. Policy documents override SOPs
3. Newer versions override older versions
4. Actual execution overrides written theory

Identify conflicts and resolve them. Return a JSON object:

{{
  "conflicts": [
    {{
      "issue": "Description of conflict",
      "documents": ["Doc A", "Doc B"],
      "chosen_path": "Which document's approach was chosen",
      "justification": "Why this was chosen",
      "rule_applied": "Compliance > Policy > SOP"
    }}
  ],
  "resolved_authority": "Primary document to cite as authority"
}}

Return JSON only, no explanation.
"""
        
        response = self.model.generate_content(prompt)
        
        try:
            conflicts = json.loads(response.text)
            return conflicts
        except json.JSONDecodeError:
            return {
                'conflicts': [],
                'resolved_authority': documents[0].get('metadata', {}).get('owner', 'Unknown')
            }
    
    def merge_business_events(self, documents: List[Dict[str, Any]]) -> List[str]:
        """Merge business events from multiple documents"""
        all_events = []
        for doc in documents:
            all_events.extend(doc.get('business_events', []))
        
        # Deduplicate while preserving order
        seen = set()
        unique_events = []
        for event in all_events:
            if event.lower() not in seen:
                seen.add(event.lower())
                unique_events.append(event)
        
        return unique_events
    
    def generate_comprehensive_ebcl(self, 
                                    merged_table: List[Dict[str, Any]],
                                    business_events: List[str],
                                    conflicts: Dict[str, Any],
                                    documents: List[Dict[str, Any]]) -> str:
        """
        Generate comprehensive EBCL from merged workflow
        """
        # Collect all metadata
        all_metadata = {
            'document_types': [d['document_type'] for d in documents],
            'versions': [d.get('metadata', {}).get('version', 'unknown') for d in documents],
            'owners': list(set([d.get('metadata', {}).get('owner', 'unknown') for d in documents])),
            'authority': conflicts.get('resolved_authority', 'Multiple Documents'),
            'source_documents': [
                d['document_type'] + ' v' + str(d.get('metadata', {}).get('version', '?'))
                for d in documents
            ]
        }
        
        prompt = f"""
You are generating a comprehensive EBCL activity from multiple merged business documents.

Merged Process Table:
{json.dumps(merged_table, indent=2)}

Business Events:
{json.dumps(business_events, indent=2)}

Conflict Resolutions:
{json.dumps(conflicts, indent=2)}

Document Metadata:
{json.dumps(all_metadata, indent=2)}

Generate a complete, comprehensive EBCL activity that:
1. Incorporates all unique steps from the merged process table
2. References all source documents in AUTHORITY
3. Includes conflict resolutions as comments
4. Handles all identified business events
5. Includes comprehensive VALIDATE rules from all documents
6. Includes all decision paths (DECIDE block)
7. Specifies all actions (ACT block)

EBCL Template:
```ebcl
ACTIVITY "Activity_Name"

OWNER <Primary Owner>
VERSION 1.0
AUTHORITY "<List all source documents>"

# Conflict Resolutions:
# - <Conflict 1>: <Resolution>
# - <Conflict 2>: <Resolution>

TRIGGER
    ON Event.<PrimaryBusinessEvent>

VALIDATE
    # From <Source Document>
    REQUIRE <condition>
    # From <Source Document>
    REQUIRE <condition>

DECIDE
    IF <condition>
        OUTCOME <OutcomeName>
    ELSE IF <condition>
        OUTCOME <OutcomeName>
    ELSE
        OUTCOME <OutcomeName>

ACT
    <OutcomeName>:
        SYSTEM <System>.<Action>
        SYSTEM NOTIFY <Actor>
    <OutcomeName>:
        HUMAN <Actor>.<Action>
        SYSTEM WAIT Approval
        SYSTEM <System>.<Action>

EVIDENCE
    LOG decision
    LOG policy_reference
    LOG source_documents
    LOG conflict_resolutions
    LOG timestamps
    STORE immutable

EXCEPTION <ExceptionName>
    WHEN <condition>
    ACT
        SYSTEM NOTIFY <Actor>
        SYSTEM BLOCK transaction
    EVIDENCE
        LOG exception_reason

SLA
    <OutcomeName> WITHIN <duration>

ESCALATION
    ON SLA.BREACH
        SYSTEM NOTIFY <Escalation Actor>
```

Generate the complete EBCL code. Return ONLY the EBCL code, no explanation.
"""
        
        response = self.model.generate_content(prompt)
        
        ebcl_code = response.text.strip()
        
        # Remove markdown code fences
        if ebcl_code.startswith('```'):
            lines = ebcl_code.split('\n')
            ebcl_code = '\n'.join(lines[1:-1])
        
        return ebcl_code
    
    def merge_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Complete multi-document merge pipeline
        
        Args:
            documents: List of documents with process_table, business_events, metadata
        
        Returns:
            Merged workflow with comprehensive EBCL
        """
        print(f"Merging {len(documents)} documents...")
        
        # Step 1: Merge process tables
        print("Step 1: Merging process tables...")
        merged_table = self.merge_process_tables(documents)
        
        # Step 2: Resolve conflicts
        print("Step 2: Resolving conflicts...")
        conflicts = self.resolve_conflicts(documents)
        
        # Step 3: Merge business events
        print("Step 3: Merging business events...")
        business_events = self.merge_business_events(documents)
        
        # Step 4: Generate comprehensive EBCL
        print("Step 4: Generating comprehensive EBCL...")
        ebcl_template = self.generate_comprehensive_ebcl(
            merged_table, business_events, conflicts, documents
        )
        
        return {
            'merged_process_table': merged_table,
            'business_events': business_events,
            'conflicts': conflicts,
            'ebcl_template': ebcl_template,
            'source_documents': [
                {
                    'type': d['document_type'],
                    'version': d.get('metadata', {}).get('version'),
                    'filename': d.get('metadata', {}).get('filename')
                }
                for d in documents
            ]
        }


# Example usage
if __name__ == "__main__":
    merger = WorkflowMerger(
        project_id=os.getenv('GOOGLE_CLOUD_PROJECT'),
        location='us-central1'
    )
    
    # Example: Merge SOP + Policy + RACI
    documents = [
        {
            'document_type': 'SOP',
            'process_table': [...],
            'business_events': [...],
            'metadata': {'version': '3.2', 'owner': 'Finance', 'filename': 'sop.txt'}
        },
        {
            'document_type': 'Policy',
            'process_table': [...],
            'business_events': [...],
            'metadata': {'version': '2.1', 'owner': 'Compliance', 'filename': 'policy.txt'}
        }
    ]
    
    result = merger.merge_documents(documents)
    
    print("Merged Process Table:")
    print(json.dumps(result['merged_process_table'], indent=2))
    
    print("\nConflicts:")
    print(json.dumps(result['conflicts'], indent=2))
    
    print("\nComprehensive EBCL:")
    print(result['ebcl_template'])
