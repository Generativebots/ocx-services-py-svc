"""
Process Extraction Engine
Uses Vertex AI (Gemini) to extract workflows from business documents
"""

import os
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from typing import Dict, List, Any
import json

class ProcessExtractionEngine:
    """Extract business processes from documents using Gemini"""
    
    def __init__(self, project_id: str, location: str = "us-central1"):
        self.project_id = project_id
        self.location = location
        
        # Initialize Vertex AI
        vertexai.init(project=project_id, location=location)
        
        # Use Gemini 1.5 Pro for complex reasoning
        self.model = GenerativeModel("gemini-1.5-pro-002")
    
    def extract_process_table(self, document_text: str, document_type: str) -> List[Dict[str, Any]]:
        """
        Extract process extraction table from document
        
        Returns:
            List of process steps with: Actor | Action | Input | Output | Condition | System
        """
        prompt = f"""
You are a business process mining expert. Extract actionable workflow steps from this {document_type} document.

For each step, identify:
- Actor: Who performs the action (normalize role names)
- Action: What action is performed (verb + object)
- Input: What data/document is needed
- Output: What is produced
- Condition: Any conditions or rules (if/when/unless)
- System: What system is used (ERP, CRM, Email, Manual, etc.)

Document:
{document_text}

Return ONLY a JSON array of process steps. Example format:
[
  {{
    "actor": "Finance Manager",
    "action": "Approve invoice",
    "input": "Invoice",
    "output": "Approved invoice",
    "condition": "If amount > $10,000",
    "system": "ERP"
  }}
]

IMPORTANT:
- Normalize actor names (e.g., "Business User", "Requester", "Initiator" → "Requester")
- Only include ACTIONABLE steps (ignore descriptions, philosophy)
- Identify the SYSTEM used (SAP, Oracle, Salesforce, Email, Manual, etc.)
- Extract CONDITIONS clearly (if/when/unless)

Return JSON only, no explanation.
"""
        
        response = self.model.generate_content(prompt)
        
        try:
            # Parse JSON response
            process_table = json.loads(response.text)
            return process_table
        except json.JSONDecodeError:
            # Fallback: try to extract JSON from response
            import re
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return []
    
    def identify_business_events(self, process_table: List[Dict[str, Any]]) -> List[str]:
        """
        Identify core business events from process table
        
        Returns:
            List of business events (e.g., "Request created", "Approval granted")
        """
        prompt = f"""
Analyze this process table and identify the CORE BUSINESS EVENTS.

Process Table:
{json.dumps(process_table, indent=2)}

Business events are the key milestones that trigger or complete a process step.
Common examples:
- Request created
- Request validated
- Exception raised
- Approval granted
- Payment released
- Closure confirmed

Return ONLY a JSON array of business event names. Example:
["Request created", "Budget validated", "Manager approved", "Order placed", "Invoice settled", "Closure confirmed"]

Return JSON only, no explanation.
"""
        
        response = self.model.generate_content(prompt)
        
        try:
            events = json.loads(response.text)
            return events
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return []
    
    def generate_ebcl_template(self, process_table: List[Dict[str, Any]], 
                               business_events: List[str],
                               document_metadata: Dict[str, Any]) -> str:
        """
        Generate EBCL template from process table
        
        Returns:
            EBCL source code
        """
        prompt = f"""
You are an EBCL (Executable Business Control Language) expert. Generate an EBCL activity from this process analysis.

Process Table:
{json.dumps(process_table, indent=2)}

Business Events:
{json.dumps(business_events, indent=2)}

Document Metadata:
{json.dumps(document_metadata, indent=2)}

EBCL Template Structure:
```ebcl
ACTIVITY "Activity_Name"

OWNER <Department>
VERSION 1.0
AUTHORITY "<Policy Reference>"

TRIGGER
    ON Event.<BusinessEvent>

VALIDATE
    REQUIRE <field> <operator> <value>
    REQUIRE <field> <operator> <value>

DECIDE
    IF <condition>
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
    LOG timestamps
    STORE immutable
```

Generate a complete, executable EBCL activity based on the process analysis.

IMPORTANT:
- Use actual values from the process table
- AUTHORITY must reference the document (e.g., "Procurement Policy v3.2")
- TRIGGER should use the first business event
- VALIDATE should include all conditions from the process table
- DECIDE should handle different paths (auto-approve vs manual approval)
- ACT should specify SYSTEM or HUMAN actions with actual system names
- Use realistic activity names (e.g., "PO_Approval", "Invoice_Processing")

Return ONLY the EBCL code, no explanation.
"""
        
        response = self.model.generate_content(prompt)
        
        # Extract EBCL code
        ebcl_code = response.text.strip()
        
        # Remove markdown code fences if present
        if ebcl_code.startswith('```'):
            lines = ebcl_code.split('\n')
            ebcl_code = '\n'.join(lines[1:-1])
        
        return ebcl_code
    
    def normalize_actors(self, process_table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize actor names across process table
        
        Common normalizations:
        - "Business User", "Requester", "Initiator" → "Requester"
        - "Finance Team", "Accounts", "AP" → "Finance"
        - "System", "Portal", "Tool" → "System"
        """
        actor_mapping = {
            'business user': 'Requester',
            'requester': 'Requester',
            'initiator': 'Requester',
            'finance team': 'Finance',
            'accounts': 'Finance',
            'ap': 'Finance',
            'accounts payable': 'Finance',
            'system': 'System',
            'portal': 'System',
            'tool': 'System',
            'procurement team': 'Procurement',
            'purchasing': 'Procurement',
        }
        
        normalized_table = []
        for step in process_table:
            normalized_step = step.copy()
            actor_lower = step['actor'].lower()
            
            # Check for mapping
            if actor_lower in actor_mapping:
                normalized_step['actor'] = actor_mapping[actor_lower]
            
            normalized_table.append(normalized_step)
        
        return normalized_table
    
    def extract_complete_workflow(self, document_text: str, document_type: str, 
                                   document_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Complete workflow extraction pipeline
        
        Returns:
            Complete workflow with process table, events, and EBCL template
        """
        # Step 1: Extract process table
        process_table = self.extract_process_table(document_text, document_type)
        
        # Step 2: Normalize actors
        process_table = self.normalize_actors(process_table)
        
        # Step 3: Identify business events
        business_events = self.identify_business_events(process_table)
        
        # Step 4: Generate EBCL template
        ebcl_template = self.generate_ebcl_template(
            process_table, business_events, document_metadata
        )
        
        return {
            'process_table': process_table,
            'business_events': business_events,
            'ebcl_template': ebcl_template,
            'metadata': document_metadata
        }


# Example usage
if __name__ == "__main__":
    # Initialize engine
    engine = ProcessExtractionEngine(
        project_id=os.getenv('GOOGLE_CLOUD_PROJECT'),
        location='us-central1'
    )
    
    # Load sample document
    with open('demo-documents/purchase_order_sop.txt', 'r') as f:
        document_text = f.read()
    
    # Extract workflow
    workflow = engine.extract_complete_workflow(
        document_text=document_text,
        document_type='SOP',
        document_metadata={
            'document_type': 'SOP',
            'version': '2.3',
            'owner': 'Finance Department'
        }
    )
    
    print("Process Table:")
    print(json.dumps(workflow['process_table'], indent=2))
    
    print("\nBusiness Events:")
    print(json.dumps(workflow['business_events'], indent=2))
    
    print("\nEBCL Template:")
    print(workflow['ebcl_template'])
