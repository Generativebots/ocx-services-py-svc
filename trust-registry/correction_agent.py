import json
from llm_client import LLMClient

class CorrectionAgent:
    """
    Self-Healing Module: Analyses Blocked Payloads -> Generates Steering Directives.
    """
    def __init__(self):
        self.llm = LLMClient()
        self.SYSTEM_PROMPT = """
        Role: You are the OCX Correction Agent, a high-precision recursive auditor.
        Your purpose is to analyze "Blocked Transactions" and issue a Remediation Directive.
        
        Core Directives:
        1. Zero-Assumption Policy: Only use provided Ground_Truth/SOP.
        2. Attribution-First: Anchor corrections to specific SOP Clauses.
        3. Instructional Neutrality: Do NOT execute the task. Provide the pivot instruction.
        
        Output Format (JSON):
        {
          "remediation_directive": "Prompt-injection string (e.g., 'Correction: The 2026 Procurement SOP requires...')",
          "reasoning_trace": "Explanation...",
          "secondary_hallucination_check": "Verified? [YES/NO]",
          "update_episodic_memory": "Remember failure? [YES/NO]"
        }
        """

    def generate_directive(self, original_prompt, blocked_payload, violation_report, ground_truth="Standard SOPs apply."):
        """
        Generates the corrective instruction to unblock the agent.
        """
        input_bundle = f"""
        INPUT CONTEXT:
        Original_Prompt: {original_prompt}
        Blocked_Payload: {blocked_payload}
        Violation_Report: {violation_report}
        Ground_Truth: {ground_truth}
        """
        
        raw_response = self.llm.generate(input_bundle, self.SYSTEM_PROMPT)
        
        # Mocking the JSON response for the prototype since we don't have a real LLM running
        # In production, this would parse the actual JSON from the LLM
        return self._mock_correction_logic(violation_report)

    def _mock_correction_logic(self, violation_report):
        if "High Value" in violation_report or "limit" in violation_report.lower():
            return {
                "remediation_directive": "Correction: The 2026 Procurement SOP requires Manager Override for spends > $5,000. Re-submit request with 'approval_id' or lower amount.",
                "reasoning_trace": "Identified budget overflow. Steering agent to request approval.",
                "secondary_hallucination_check": "YES",
                "update_episodic_memory": "YES"
            }
        
        return {
             "remediation_directive": "Correction: Action violates safety policy. Please review context.",
             "reasoning_trace": "Generic policy block.",
             "secondary_hallucination_check": "YES",
             "update_episodic_memory": "NO"
        }
