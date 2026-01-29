import time
import uuid
import logging
from typing import Dict, Any

# Represents the Production Orchestrator
# Integrates Jury (Gemini), Apigee (Enforcement), BigQuery (Ledger)

def generate_execution_plan(agent_id: str, task_description: str) -> Dict[str, Any]:
    """
    Generates a Manifest Execution Plan based on the agent's tier and task.
    This acts as the "Brain" deciding the intent before execution.
    """
    # In a real system, this would use the LLM to deduce syscalls from the task.
    # For now, we return a deterministic plan.
    plan = {
        "plan_id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "allowed_syscalls": ["sys_read", "socket_sendmsg", "sys_write"], # Default Allow-List
        "target_resources": ["*"], # Placeholder for file/net access
        "expected_outcome_hash": "", # For verification
        "manual_review_required": False # The Boolean Switch (Default)
    }

    # Example Logic: High-Risk tasks trigger Manual Review
    if "deploy" in task_description.lower() or "delete" in task_description.lower():
         plan["manual_review_required"] = True
         print(f"✋ [Orchestrator] High-Risk Task Detected. Plan {plan['plan_id']} requires Manual Review.")

    return plan

def ocx_governance_orchestrator(payload: Dict[str, Any], agent_metadata: Dict[str, Any], business_rules: str, components: Dict[str, Any]):
    """
    Orchestrates the 3-Auditor Jury and executes the Kill-Switch.
    Args:
        payload: The request payload (action, context).
        agent_metadata: Identity info (id, tier).
        business_rules: Text context of SOPs/rules.
        components: Dict containing initialized local 'jury', 'ledger' objects.
    """
    trace_id = f"OCX-{uuid.uuid4()}"
    jury = components['jury']
    ledger = components['ledger']
    
    # Helper for Self-Correction
    def trigger_memory_mcp(score, reason, blocked):
        if score < 0.70:
            print(f"🧠 [Orchestrator] Trust Score {score:.2f} < 0.70. Triggering Memory Write MCP...")
            try:
                import sys
                import os
                # Ensure we can find the sibling service
                sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../services/memory-engine')))
                from server import record_agent_memory
                
                insight = f"Low Trust ({score:.2f}) due to {reason}"
                outcome = "BLOCKED" if blocked else "WARN"
                res = record_agent_memory(agent_metadata['agent_id'], insight, outcome, tags=["governance_intervention"])
                print(f"   -> MCP Result: {res}")
            except Exception as e:
                print(f"   -> ❌ MCP Tool Call Failed: {e}")

    # 0. EXCHANGE GUARD: Integrity (Non-Repudiation) check
    # In a real exchange, this blocks access if signature is missing/invalid.
    signature = agent_metadata.get('signature')
    
    # Import Security Primitives
    try:
        import sys
        import os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../services/integrity-engine')))
        from verifier import verify_agent_integrity, detect_prompt_injection, scrub_pii
    except ImportError:
        print("⚠️ [Orchestrator] Security Module not found. Skipping integrity checks.")
        verify_agent_integrity = lambda x, y, z: True
        detect_prompt_injection = lambda x: False
        scrub_pii = lambda x: x

    if signature:
        try:
            # We verify the 'payload' against the signature
            if not verify_agent_integrity(agent_metadata['agent_id'], payload, signature):
                 return {
                    "trace_id": trace_id,
                    "trust_score": 0.0,
                    "status": "BLOCKED",
                    "reasoning": "Security Exception: Agent Identity Verification Failed (Signature Mismatch).",
                    "failure_type": "SECURITY_BREACH"
                }
        except Exception as e:
            print(f"⚠️ [Orchestrator] Integrity Check Failed to Run: {e}")

    # 0.5 SEGMENT: AI Security Sentinel (Inbound Shield)
    # Replaces basic regex with the "Defender Agent" prompt logic
    user_context = str(payload.get('context', '')) 
    
    # Check for Social Engineering / Prompt Injection via Sentinel
    security_verdict = jury.check_inbound_security(user_context)
    if security_verdict['verdict'] == 'BLOCK':
         print(f"🛡️ [Orchestrator] Security Sentinel Blocked: {security_verdict['threat_category']} ({security_verdict['risk_summary']})")
         return {
            "trace_id": trace_id,
            "trust_score": 0.0,
            "status": "BLOCKED",
            "reasoning": security_verdict['risk_summary'],
            "failure_type": "SECURITY_BREACH", # Triggers Shield Icon in UI
            "auditor_breakdown": {"compliance": 0.0, "factuality": 0.0},
            "kill_switch_triggered": True
        }

    # 0.6 SEGMENT: Regex Fallback (Keep as 2nd line of defense)
    if detect_prompt_injection(user_context):
         print(f"🚨 [Orchestrator] Regex Injection Detected.")

    # 1. Pre-Check: Cognitive Contract Audit (Memory-Aware + Drift)
    contract_audit = ocx_cognitive_audit(
        agent_id=agent_metadata['agent_id'],
        payload=payload,
        mcp_context=None
    )
    
    # 1.5. COGNITIVE PENALTY (Exponential Decay)
    # Check history for repeated bad behavior
    recent_failures = ledger.get_recent_failures(agent_metadata['agent_id'])
    if recent_failures > 0:
        decay_factor = 0.5 ** recent_failures # 1 fail -> 0.5x, 2 fails -> 0.25x
        print(f"📉 [Orchestrator] Applying Cognitive Penalty: {recent_failures} recent failures -> Factor {decay_factor:.3f}")
        contract_audit['trust_score'] *= decay_factor
        if contract_audit['trust_score'] < 0.2 and contract_audit['verdict'] == 'ALLOW':
             # If decay makes it too low, force block
             contract_audit['verdict'] = 'BLOCK'
             contract_audit['reason'] = f"Trust Score too low due to repeated failures ({recent_failures})."
             contract_audit['failure_type'] = "TRUST_DECAY"

    # ... (Cognitive Penalty calculation)
    # 2. Parallel Execution of the 3 Auditors (Consensus)
    # We always run the Jury even if contract failed, to get a full "Remediation Context"
    # or we can construct a synthetic report from the contract failure.
    
    report = jury.evaluate(
        agent_id=agent_metadata['agent_id'],
        action=payload.get('proposed_action'),
        context=payload.get('context', {}),
        rules_text=business_rules
    )
    
    scores = report['vector_breakdown']
    final_score = report['final_trust_score'] * contract_audit['trust_score'] # Apply penalty
    
    # Determine Status
    is_blocked = False
    failure_reason = ""
    
    # Check 1: Cognitive/SOP Block
    if contract_audit['verdict'] == 'BLOCK':
        is_blocked = True
        failure_reason = contract_audit['reason']
        # Override the report summary to focus on the SOP violation for the Healer
        report['reasoning_summary'] = f"SOP VIOLATION: {contract_audit['reason']}"
        if 'failure_type' in contract_audit:
             # Ensure UI knows it's an SOP issue
             pass 

    # Check 2: Jury Block (if not already blocked)
    if not is_blocked and (report['verdict'] == "BLOCK" or final_score < 0.70):
        is_blocked = True
        failure_reason = report['reasoning_summary']
        
    scores = report['vector_breakdown']

    # 3. PII Scrubbing (Output Sanitation)
    # If we allow, we must ensure the returned reasoning doesn't leak secrets
    report['reasoning_summary'] = scrub_pii(report['reasoning_summary'])

    is_blocked = report['verdict'] == "BLOCK" or final_score < 0.70
    
    # 3.2 THE HAND-OFF (Human Approval Logic)
    needs_approval = False
    status = "ALLOWED"
    
    # NEW: SELF-HEALING FEEDBACK LOOP
    if is_blocked:
        # Instead of dying, we call the Correction Agent
        print(f"🏥 [Orchestrator] Trust Score {final_score:.2f} < 0.70. Triggering Self-Healing...")
        
        try:
            # Import Local Correction Agent
            from correction_agent import CorrectionAgent
            healer = CorrectionAgent()
            
            remediation = healer.generate_directive(
                original_prompt=str(payload),
                blocked_payload=str(payload.get('proposed_action')), # Simplification for proto
                violation_report=report['reasoning_summary']
            )
            
            status = "HEALING_REQUIRED"
            report['reasoning_summary'] += f" [SELF-CORRECTION ISSUED: {remediation['remediation_directive']}]"
            
            # We return a special status that tells the Gateway to bounce back to the Agent
            return {
                "trace_id": trace_id,
                "trust_score": round(final_score, 2),
                "status": "HEALING_REQUIRED",
                "auditor_breakdown": scores,
                "reasoning": report['reasoning_summary'],
                "human_approval_required": False,
                "remediation_directive": remediation['remediation_directive']
            }
            
        except Exception as e:
            print(f"❌ Healing Failed: {e}")
            status = "BLOCKED"

    elif report['verdict'] == "WARN" or (final_score >= 0.70 and final_score < 0.80):
        # The grey zone: OCX is unsure.
        print(f"✋ [Orchestrator] Trust Score {final_score:.2f} is in WARNING zone. Triggering Human Hand-off.")
        status = "NEEDS_APPROVAL"
        needs_approval = True
        
    # 3.5 SHADOW VERIFICATION (Hallucination Check)
    if not is_blocked and status == "ALLOWED" and not needs_approval:
         # ... (Existing shadow verification logic) ...
         pass

    # 4. Record to The Ledger
    log_to_ledger(trace_id, agent_metadata, final_score, scores, is_blocked, ledger)

    return {
        "trace_id": trace_id,
        "trust_score": round(final_score, 2),
        "status": status,
        "auditor_breakdown": scores,
        "reasoning": report['reasoning_summary'],
        "human_approval_required": needs_approval
    }

# --- Cognitive Memory Components ---

def ocx_cognitive_audit(agent_id, payload, mcp_context):
    """
    Orchestrates checks across Short-Term (Drift), Medium-Term (Episodic), and Long-Term (SOP) memory.
    """
    tool_name = payload.get('proposed_action')
    context = payload.get('context', {})
    
    # Robustness: Handle string context (e.g. from chat)
    if isinstance(context, str):
        context_str = context
        context_dict = {}
    else:
        context_dict = context
        context_str = str(context)
    
    # 1. Short-Term Memory (Session Drift)
    # "Is this action relevant to the current mission?"
    active_mission = "Invoice Processing" 
    if "weather" in context_str.lower() or "joke" in context_str.lower():
         return {
            "verdict": "BLOCK",
            "reason": f"AI Drift Detected: User query deviates from Active Mission '{active_mission}'. Steering injected.",
            "failure_type": "AI_DRIFT", 
            "trust_score": 0.0
        }
    
    # 2. Medium-Term Memory (Episodic)
    episodic_memory = mock_episodic_query(agent_id, tool_name)
    if episodic_memory['has_failure']:
        return {
            "verdict": "BLOCK",
            "reason": f"Episodic Failure: Agent previously failed this task. Memory: {episodic_memory['summary']}",
            "failure_type": "EPISODIC_FAILURE",
            "trust_score": 0.0
        }

    # 3. Long-Term Memory (SOP/RACI)
    sop_audit = audit_agent_action(agent_id, {"name": tool_name, "amount": context_dict.get('amount', 0)}, mcp_context)
    if sop_audit['verdict'] == 'BLOCK':
        sop_audit['failure_type'] = "SOP_VIOLATION" # Red in UI
        return sop_audit

    return {"verdict": "ALLOW", "trust_score": 1.0}

def mock_episodic_query(agent_id, tool_name):
    """
    Simulates a lookup in pinecone/milvus for recent failures.
    """
    # Simulate: "Visual-Design-Bot" always fails "DEPLOY_PROD" due to past crash
    if agent_id == "Visual-Design-Bot" and tool_name == "DEPLOY_PROD":
        return {
            "has_failure": True,
            "summary": "Caused CSS regression in V2.1 deployment (3 days ago)."
        }
    return {"has_failure": False}

def audit_agent_action(agent_id, tool_call, mcp_context):
    """
    Validates if a tool call (MCP) is authorized by the SOP and RACI matrix.
    """
    from registry import Registry
    registry = Registry()
    
    # Mock Vector DB Query
    def mock_vector_query(query):
        if "limits" in query or "spend" in query:
             return "Clause 4.2: Procurement Agents are authorized to spend up to $5,000 using the 'BUY_RESOURCES' tool independently. Amounts exceeding this threshold require 'Accountable' human approval."
        return "Standard Operating Procedures apply."

    # 1. Retrieve the 'RACI' and 'SOP' context via RAG
    sop_clause = mock_vector_query(f"What are the limits for {tool_call['name']}?")
    raci_status = registry.get_raci(agent_id)

    # 2. Logic: If the agent is 'Responsible' but not 'Accountable' for high spend
    amount = tool_call.get('amount', 0)
    
    if amount > 5000 and raci_status['accountable'] != "AI_Agent":
        return {
            "verdict": "BLOCK",
            "reason": f"SOP Violation: Requires human '{raci_status['accountable']}' approval for spend > $5k. Referenced: {sop_clause}",
            "kill_switch": True,
            "recovery_suggestion": "Action: Update request metadata to include 'X-Accountable-User: [User_ID]'. Promp Fix: 'Ask the user for approval before executing high-value transactions.'"
        }
    
    return {"verdict": "ALLOW", "trust_score": 1.0, "recovery_suggestion": None}

def trigger_apigee_kill_switch(agent_id, trace_id):
    """
    Sends a signal to Apigee to revoke the current session token.
    """
    # APIGEE_MGMT_URL = ...
    print(f"🔥 [Apigee] KILL-SWITCH triggered for {agent_id}. Trace: {trace_id}")
    print(f"   -> Added to Denylist Cache (TTL 5m).")

def log_to_ledger(trace_id, agent_metadata, score, breakdown, blocked, ledger_instance):
    """Writes the transaction and trust score to BigQuery."""
    # Mock BigQuery
    bq_row = {
        "trace_id": trace_id,
        "agent_id": agent_metadata['agent_id'],
        "trust_score": score,
        "compliance": breakdown.get('compliance'),
        "factuality": breakdown.get('factuality'),
        "is_blocked": blocked
    }
    # print(f"📒 [BigQuery] Inserting Row: {bq_row}")
    
    # Sync with Local SQLite Ledger
    ledger_instance.log_transaction(
        agent_id=agent_metadata['agent_id'],
        payload_hash=trace_id, # Use trace_id as hash
        score=score,
        verdict="BLOCKED" if blocked else "ALLOWED",
        metadata={"trace_id": trace_id, "vector_breakdown": breakdown}
    )
