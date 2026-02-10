"""
Enhanced Socket Interceptor
Activity-aware interception with real-time compliance enforcement

Intercepts socket operations and applies VALIDATE rules from Activity Registry
"""

import socket
import json
import threading
import time
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import requests
import logging

import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration — from environment variables
ACTIVITY_REGISTRY_URL = os.getenv("ACTIVITY_REGISTRY_URL", "http://localhost:8002")
EVIDENCE_VAULT_URL = os.getenv("EVIDENCE_VAULT_URL", "http://localhost:8003")

@dataclass
class ValidationRule:
    """VALIDATE rule from EBCL activity"""
    rule_id: str
    condition: str
    activity_id: str
    activity_name: str
    policy_reference: str
    severity: str = "ERROR"  # ERROR, WARNING, INFO

@dataclass
class InterceptionContext:
    """Context for socket interception"""
    socket_id: str
    operation: str  # connect, send, recv, close
    destination: tuple  # (host, port)
    data: Optional[bytes]
    timestamp: datetime
    agent_id: str
    tenant_id: str

class ActivityRegistry:
    """Client for Activity Registry"""
    
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
    
    def get_active_activities(self, tenant_id: str, environment: str = "PROD") -> list:
        """Get all active activities for tenant"""
        cache_key = f"{tenant_id}:{environment}"
        
        # Check cache
        if cache_key in self._cache:
            cached_data, cached_time = self._cache[cache_key]
            if time.time() - cached_time < self._cache_ttl:
                return cached_data
        
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/activities",
                params={"status": "ACTIVE"}
            )
            response.raise_for_status()
            activities = response.json()
            
            # Cache result
            self._cache[cache_key] = (activities, time.time())
            return activities
        except Exception as e:
            logger.error(f"Failed to fetch activities: {e}")
            return []
    
    def parse_validate_rules(self, ebcl_source: str, activity_id: str, activity_name: str, policy_ref: str) -> list:
        """Parse VALIDATE rules from EBCL source"""
        rules = []
        
        # Simple parser for VALIDATE block
        if "VALIDATE" not in ebcl_source:
            return rules
        
        validate_section = ebcl_source.split("VALIDATE")[1].split("\n\n")[0]
        
        for line in validate_section.split("\n"):
            line = line.strip()
            if line.startswith("REQUIRE"):
                condition = line.replace("REQUIRE", "").strip()
                rules.append(ValidationRule(
                    rule_id=f"{activity_id}:{len(rules)}",
                    condition=condition,
                    activity_id=activity_id,
                    activity_name=activity_name,
                    policy_reference=policy_ref,
                    severity="ERROR"
                ))
        
        return rules

class EvidenceVault:
    """Client for Evidence Vault"""
    
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
    
    def log_violation(self, context: InterceptionContext, rule: ValidationRule, reason: str) -> None:
        """Log compliance violation to Evidence Vault"""
        try:
            evidence = {
                "activity_id": rule.activity_id,
                "activity_name": rule.activity_name,
                "activity_version": "1.0.0",
                "execution_id": context.socket_id,
                "agent_id": context.agent_id,
                "agent_type": "SYSTEM",
                "tenant_id": context.tenant_id,
                "environment": "PROD",
                "event_type": "EXCEPTION",
                "event_data": {
                    "violation_type": "SOCKET_INTERCEPTION",
                    "operation": context.operation,
                    "destination": f"{context.destination[0]}:{context.destination[1]}",
                    "rule_violated": rule.condition,
                    "reason": reason,
                    "timestamp": context.timestamp.isoformat()
                },
                "decision": f"Blocked: {reason}",
                "outcome": "BLOCKED",
                "policy_reference": rule.policy_reference
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/evidence",
                json=evidence
            )
            response.raise_for_status()
            logger.info(f"Violation logged: {rule.rule_id}")
        except Exception as e:
            logger.error(f"Failed to log violation: {e}")

class SocketInterceptor:
    """
    Enhanced Socket Interceptor with Activity-Aware Compliance
    
    Intercepts socket operations and applies VALIDATE rules from Activity Registry
    """
    
    def __init__(self, tenant_id: str, agent_id: str) -> None:
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.activity_registry = ActivityRegistry(ACTIVITY_REGISTRY_URL)
        self.evidence_vault = EvidenceVault(EVIDENCE_VAULT_URL)
        self.validation_rules = []
        self._original_socket = socket.socket
        self._lock = threading.Lock()
        
        # Load validation rules
        self._load_validation_rules()
        
        # Start background rule refresh
        self._start_rule_refresh()
    
    def _load_validation_rules(self) -> None:
        """Load VALIDATE rules from Activity Registry"""
        logger.info(f"Loading validation rules for tenant {self.tenant_id}")
        
        activities = self.activity_registry.get_active_activities(self.tenant_id)
        
        with self._lock:
            self.validation_rules = []
            for activity in activities:
                rules = self.activity_registry.parse_validate_rules(
                    activity['ebcl_source'],
                    activity['activity_id'],
                    activity['name'],
                    activity['authority']
                )
                self.validation_rules.extend(rules)
        
        logger.info(f"Loaded {len(self.validation_rules)} validation rules")
    
    def _start_rule_refresh(self) -> None:
        """Start background thread to refresh rules periodically"""
        def refresh_loop() -> None:
            while True:
                time.sleep(300)  # Refresh every 5 minutes
                self._load_validation_rules()
        
        thread = threading.Thread(target=refresh_loop, daemon=True)
        thread.start()
    
    def _evaluate_rule(self, rule: ValidationRule, context: InterceptionContext) -> tuple:
        """
        Evaluate validation rule against context
        
        Returns: (passed: bool, reason: str)
        """
        # Simple rule evaluation (in production, use a proper expression evaluator)
        
        # Example rules:
        # - "destination.port != 22" (block SSH)
        # - "destination.host not in blacklist"
        # - "data.size < 1MB"
        
        try:
            # Extract variables from context
            variables = {
                'destination': {
                    'host': context.destination[0],
                    'port': context.destination[1]
                },
                'operation': context.operation,
                'agent_id': context.agent_id,
                'tenant_id': context.tenant_id
            }
            
            # Simple condition evaluation
            condition = rule.condition.lower()
            
            # Check for common patterns
            if 'port' in condition:
                if '!=' in condition:
                    port = int(condition.split('!=')[1].strip())
                    if context.destination[1] == port:
                        return False, f"Port {port} is blocked by policy"
                elif '==' in condition:
                    port = int(condition.split('==')[1].strip())
                    if context.destination[1] != port:
                        return False, f"Only port {port} is allowed"
            
            if 'host' in condition and 'blacklist' in condition:
                # In production, check against actual blacklist
                blacklist = ['malicious.com', 'blocked.net']
                if context.destination[0] in blacklist:
                    return False, f"Host {context.destination[0]} is blacklisted"
            
            return True, "Rule passed"
        
        except Exception as e:
            logger.error(f"Rule evaluation error: {e}")
            return True, "Rule evaluation failed (allowing)"
    
    def _check_compliance(self, context: InterceptionContext) -> tuple:
        """
        Check if operation complies with all validation rules
        
        Returns: (compliant: bool, violations: list)
        """
        violations = []
        
        with self._lock:
            for rule in self.validation_rules:
                passed, reason = self._evaluate_rule(rule, context)
                if not passed:
                    violations.append((rule, reason))
                    
                    # Log violation
                    self.evidence_vault.log_violation(context, rule, reason)
        
        return len(violations) == 0, violations
    
    def install(self) -> None:
        """Install socket interceptor"""
        logger.info("Installing socket interceptor")
        
        interceptor = self
        
        class InterceptedSocket(socket.socket):
            """Socket wrapper with interception"""
            
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                self.socket_id = f"sock-{id(self)}"
            
            def connect(self, address) -> Any:
                """Intercept connect operation"""
                context = InterceptionContext(
                    socket_id=self.socket_id,
                    operation="connect",
                    destination=address,
                    data=None,
                    timestamp=datetime.utcnow(),
                    agent_id=interceptor.agent_id,
                    tenant_id=interceptor.tenant_id
                )
                
                # Check compliance
                compliant, violations = interceptor._check_compliance(context)
                
                if not compliant:
                    violation_msg = "; ".join([v[1] for v in violations])
                    logger.warning(f"BLOCKED: {address} - {violation_msg}")
                    raise PermissionError(f"Connection blocked by policy: {violation_msg}")
                
                logger.info(f"ALLOWED: {address}")
                return super().connect(address)
            
            def send(self, data, flags=0) -> Any:
                """Intercept send operation"""
                # Could add data inspection rules here
                return super().send(data, flags)
            
            def recv(self, bufsize, flags=0) -> Any:
                """Intercept recv operation"""
                # Could add data inspection rules here
                return super().recv(bufsize, flags)
        
        # Replace socket.socket with intercepted version
        socket.socket = InterceptedSocket
        logger.info("Socket interceptor installed")
    
    def uninstall(self) -> None:
        """Uninstall socket interceptor"""
        socket.socket = self._original_socket
        logger.info("Socket interceptor uninstalled")

# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    # Install interceptor for tenant
    interceptor = SocketInterceptor(
        tenant_id="acme-corp",
        agent_id="agent-001"
    )
    
    interceptor.install()
    
    try:
        # Test connection (will be intercepted)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("google.com", 80))  # Allowed
        s.close()
        
        # This would be blocked if rule exists
        # s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # s.connect(("malicious.com", 22))  # Blocked
        
    except PermissionError as e:
        print(f"Connection blocked: {e}")
    
    finally:
        interceptor.uninstall()
