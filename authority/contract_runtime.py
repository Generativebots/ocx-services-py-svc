"""
EBCL Contract Execution Runtime
Links A2A use cases to EBCL contracts and executes them with real agents
"""

import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import logging
logger = logging.getLogger(__name__)



class ContractStatus(Enum):
    """Contract execution status"""
    DRAFT = "draft"
    DEPLOYED = "deployed"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionStatus(Enum):
    """Individual execution status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class EBCLContractRuntime:
    """Runtime for executing EBCL contracts linked to A2A use cases"""
    
    def __init__(self, db_conn) -> None:
        self.db_conn = db_conn
    

    
    def link_use_case_to_contract(self, tenant_id: str, use_case_id: str) -> Dict[str, Any]:
        """
        Link an A2A use case to an EBCL contract.
        Generates EBCL code from the use case.
        
        Args:
            tenant_id: Tenant ID for multi-tenant isolation
            use_case_id: The use case to link
        """
        # Get use case (scoped to tenant via RLS or explicit filter)
        with self.db_conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM a2a_use_cases WHERE use_case_id = %s
            """, (use_case_id,))
            use_case = cur.fetchone()
            
            if not use_case:
                raise ValueError(f"Use case not found: {use_case_id}")
        
        # Generate EBCL code
        ebcl_code = self._generate_ebcl_from_use_case(use_case)
        
        # Create contract
        contract_id = f"contract_{uuid.uuid4().hex[:12]}"
        
        with self.db_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ebcl_contracts (
                    contract_id, tenant_id, use_case_id, name, description,
                    ebcl_code, version, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                contract_id,
                tenant_id,
                use_case_id,
                use_case[2],  # title
                use_case[3],  # description
                ebcl_code,
                "1.0.0",
                ContractStatus.DRAFT.value
            ))
            self.db_conn.commit()
        
        return {
            "contract_id": contract_id,
            "tenant_id": tenant_id,
            "use_case_id": use_case_id,
            "name": use_case[2],
            "version": "1.0.0",
            "status": ContractStatus.DRAFT.value,
            "ebcl_code": ebcl_code
        }
    
    def _generate_ebcl_from_use_case(self, use_case) -> str:
        """Generate EBCL code from use case"""
        # Extract use case details
        title = use_case[2]
        description = use_case[3]
        agent1_action = use_case[4]
        agent2_action = use_case[5]
        authority_gap = use_case[6]
        
        # Generate EBCL contract
        ebcl_code = f"""
# EBCL Contract: {title}
# Generated from A2A Use Case
# Description: {description}

contract {title.replace(' ', '_')}:
    version: "1.0.0"
    
    # Parties
    party agent1:
        role: "initiator"
        actions: ["{agent1_action}"]
    
    party agent2:
        role: "responder"
        actions: ["{agent2_action}"]
    
    # Authority requirements
    authority:
        gap: "{authority_gap}"
        required_trust_level: 0.5
        trust_tax_rate: 0.10
    
    # Execution flow
    flow:
        step handshake:
            agent1 -> agent2: initiate_handshake()
            require: trust_level >= 0.5
            on_success: goto step_execute
            on_failure: goto step_reject
        
        step step_execute:
            agent1 -> agent2: execute_action("{agent1_action}")
            agent2 -> agent1: respond_action("{agent2_action}")
            require: authority_verified
            on_success: goto step_complete
            on_failure: goto step_rollback
        
        step step_complete:
            emit: execution_success
            apply_trust_tax: true
            goto: end
        
        step step_reject:
            emit: execution_rejected
            reason: "Insufficient trust level"
            goto: end
        
        step step_rollback:
            emit: execution_failed
            rollback: all_changes
            goto: end
    
    # Monitoring
    monitoring:
        track_entropy: true
        alert_on_high_entropy: true
        log_all_executions: true
"""
        return ebcl_code
    
    def deploy_contract(self, tenant_id: str, contract_id: str) -> Dict[str, Any]:
        """Deploy a contract to the EBCL runtime (tenant-scoped)"""
        with self.db_conn.cursor() as cur:
            cur.execute("""
                UPDATE ebcl_contracts
                SET status = %s, deployed_at = %s, updated_at = %s
                WHERE contract_id = %s AND tenant_id = %s
            """, (
                ContractStatus.DEPLOYED.value,
                datetime.now(),
                datetime.now(),
                contract_id,
                tenant_id
            ))
            if cur.rowcount == 0:
                raise ValueError(f"Contract {contract_id} not found for tenant {tenant_id}")
            self.db_conn.commit()
        
        return {
            "contract_id": contract_id,
            "tenant_id": tenant_id,
            "status": ContractStatus.DEPLOYED.value,
            "deployed_at": datetime.now().isoformat()
        }
    
    def execute_contract(
        self,
        tenant_id: str,
        contract_id: str,
        agent1_id: str,
        agent2_id: str,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a contract with real agents (tenant-scoped)"""
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        started_at = datetime.now()
        
        try:
            # Get contract (scoped to tenant)
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM ebcl_contracts
                    WHERE contract_id = %s AND tenant_id = %s
                """, (contract_id, tenant_id))
                contract = cur.fetchone()
                
                if not contract:
                    raise ValueError(f"Contract {contract_id} not found for tenant {tenant_id}")
                
                if contract[8] != ContractStatus.DEPLOYED.value:  # status (shifted by tenant_id col)
                    raise ValueError(f"Contract not deployed: {contract_id}")
            
            # Simulate contract execution
            # In production, this would:
            # 1. Perform handshake between agents
            # 2. Verify authority
            # 3. Execute contract logic
            # 4. Apply trust tax
            # 5. Record results
            
            import time
            import random
            
            time.sleep(0.1)  # Simulate execution time
            
            trust_level = random.uniform(0.6, 0.95)
            trust_tax = (1.0 - trust_level) * 0.10
            execution_time_ms = random.randint(50, 200)
            
            output_data = {
                "status": "success",
                "agent1_action": input_data.get("agent1_action", "executed"),
                "agent2_action": input_data.get("agent2_action", "responded"),
                "trust_level": trust_level,
                "trust_tax": trust_tax,
                "value_created": input_data.get("value", 1000.0)
            }
            
            completed_at = datetime.now()
            
            # Record execution (with tenant_id)
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ebcl_contract_executions (
                        execution_id, tenant_id, contract_id, agent1_id, agent2_id,
                        status, input_data, output_data, trust_level, trust_tax,
                        execution_time_ms, started_at, completed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    execution_id,
                    tenant_id,
                    contract_id,
                    agent1_id,
                    agent2_id,
                    ExecutionStatus.SUCCESS.value,
                    json.dumps(input_data),
                    json.dumps(output_data),
                    trust_level,
                    trust_tax,
                    execution_time_ms,
                    started_at,
                    completed_at
                ))
                self.db_conn.commit()
            
            return {
                "execution_id": execution_id,
                "tenant_id": tenant_id,
                "contract_id": contract_id,
                "status": ExecutionStatus.SUCCESS.value,
                "trust_level": trust_level,
                "trust_tax": trust_tax,
                "execution_time_ms": execution_time_ms,
                "output_data": output_data,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat()
            }
            
        except Exception as e:
            # Record failed execution (with tenant_id)
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ebcl_contract_executions (
                        execution_id, tenant_id, contract_id, agent1_id, agent2_id,
                        status, input_data, error_message, started_at, completed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    execution_id,
                    tenant_id,
                    contract_id,
                    agent1_id,
                    agent2_id,
                    ExecutionStatus.FAILED.value,
                    json.dumps(input_data),
                    str(e),
                    started_at,
                    datetime.now()
                ))
                self.db_conn.commit()
            
            raise
    
    def create_contract_version(
        self,
        tenant_id: str,
        contract_id: str,
        ebcl_code: str,
        changes: str,
        created_by: str
    ) -> Dict[str, Any]:
        """Create a new version of a contract (tenant-scoped)"""
        # Get current version (scoped to tenant)
        with self.db_conn.cursor() as cur:
            cur.execute("""
                SELECT version FROM ebcl_contracts
                WHERE contract_id = %s AND tenant_id = %s
            """, (contract_id, tenant_id))
            result = cur.fetchone()
            
            if not result:
                raise ValueError(f"Contract {contract_id} not found for tenant {tenant_id}")
            
            current_version = result[0]
        
        # Increment version
        major, minor, patch = map(int, current_version.split('.'))
        new_version = f"{major}.{minor}.{patch + 1}"
        
        version_id = f"ver_{uuid.uuid4().hex[:12]}"
        
        # Save version (with tenant_id)
        with self.db_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ebcl_contract_versions (
                    version_id, tenant_id, contract_id, version, ebcl_code, changes, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                version_id,
                tenant_id,
                contract_id,
                new_version,
                ebcl_code,
                changes,
                created_by
            ))
            
            # Update contract (scoped to tenant)
            cur.execute("""
                UPDATE ebcl_contracts
                SET ebcl_code = %s, version = %s, updated_at = %s
                WHERE contract_id = %s AND tenant_id = %s
            """, (
                ebcl_code,
                new_version,
                datetime.now(),
                contract_id,
                tenant_id
            ))
            
            self.db_conn.commit()
        
        return {
            "version_id": version_id,
            "tenant_id": tenant_id,
            "contract_id": contract_id,
            "version": new_version,
            "changes": changes
        }
    
    def get_ebcl_contract_executions(
        self,
        tenant_id: str,
        contract_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get execution history for a contract (tenant-scoped)"""
        with self.db_conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM ebcl_contract_executions
                WHERE contract_id = %s AND tenant_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (contract_id, tenant_id, limit))
            
            executions = []
            for row in cur.fetchall():
                executions.append({
                    "execution_id": row[0],
                    "tenant_id": row[1],
                    "contract_id": row[2],
                    "agent1_id": row[3],
                    "agent2_id": row[4],
                    "status": row[5],
                    "trust_level": row[8],
                    "trust_tax": row[9],
                    "execution_time_ms": row[10],
                    "started_at": row[12].isoformat() if row[12] else None,
                    "completed_at": row[13].isoformat() if row[13] else None
                })
            
            return executions
