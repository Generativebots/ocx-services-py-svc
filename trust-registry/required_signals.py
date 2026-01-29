"""
Required Signals Verification System
Implements CTO_SIGNATURE, JURY_ENTROPY_CHECK, and other approval signals
"""

import time
import hashlib
import json
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta


class SignalType(str, Enum):
    """Types of required signals"""
    CTO_SIGNATURE = "CTO_SIGNATURE"
    JURY_ENTROPY_CHECK = "JURY_ENTROPY_CHECK"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    TWO_FACTOR_AUTH = "TWO_FACTOR_AUTH"
    COMPLIANCE_REVIEW = "COMPLIANCE_REVIEW"


@dataclass
class Signal:
    """Represents a verification signal"""
    signal_type: SignalType
    value: Any  # Signature, entropy score, approval ID, etc.
    timestamp: float
    expires_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """Check if signal has expired"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at
    
    def is_valid(self) -> bool:
        """Check if signal is valid"""
        return not self.is_expired()


class SignalCollector:
    """
    Collects and verifies required signals for policy enforcement
    
    Flow:
    1. Policy requires signals (e.g., ["CTO_SIGNATURE", "JURY_ENTROPY_CHECK"])
    2. System collects signals from various sources
    3. Verify all required signals are present and valid
    4. If all signals valid → ALLOW, else → BLOCK
    """
    
    def __init__(self):
        self.signals: Dict[str, List[Signal]] = {}  # transaction_id -> signals
    
    def add_signal(
        self,
        transaction_id: str,
        signal_type: SignalType,
        value: Any,
        ttl_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add a signal to transaction
        
        Args:
            transaction_id: Unique transaction ID
            signal_type: Type of signal
            value: Signal value (signature, score, etc.)
            ttl_seconds: Time-to-live in seconds
            metadata: Additional metadata
            
        Returns:
            True if signal added successfully
        """
        if transaction_id not in self.signals:
            self.signals[transaction_id] = []
        
        expires_at = None
        if ttl_seconds:
            expires_at = time.time() + ttl_seconds
        
        signal = Signal(
            signal_type=signal_type,
            value=value,
            timestamp=time.time(),
            expires_at=expires_at,
            metadata=metadata or {}
        )
        
        self.signals[transaction_id].append(signal)
        return True
    
    def verify_signals(
        self,
        transaction_id: str,
        required_signals: List[str]
    ) -> tuple[bool, List[str]]:
        """
        Verify all required signals are present and valid
        
        Args:
            transaction_id: Transaction to verify
            required_signals: List of required signal types
            
        Returns:
            (all_valid, missing_signals)
        """
        if transaction_id not in self.signals:
            return False, required_signals
        
        transaction_signals = self.signals[transaction_id]
        
        # Check each required signal
        missing = []
        for required in required_signals:
            # Find signal of this type
            found = False
            for signal in transaction_signals:
                if signal.signal_type.value == required and signal.is_valid():
                    found = True
                    break
            
            if not found:
                missing.append(required)
        
        return len(missing) == 0, missing
    
    def get_signals(self, transaction_id: str) -> List[Signal]:
        """Get all signals for transaction"""
        return self.signals.get(transaction_id, [])
    
    def cleanup_expired(self) -> int:
        """Remove expired signals"""
        removed = 0
        for tx_id, signals in list(self.signals.items()):
            # Remove expired signals
            valid_signals = [s for s in signals if s.is_valid()]
            removed += len(signals) - len(valid_signals)
            
            if valid_signals:
                self.signals[tx_id] = valid_signals
            else:
                del self.signals[tx_id]
        
        return removed


class CTOSignatureVerifier:
    """Verifies CTO digital signatures"""
    
    def __init__(self, cto_public_key: str):
        self.cto_public_key = cto_public_key
    
    def verify_signature(
        self,
        transaction_data: Dict[str, Any],
        signature: str
    ) -> bool:
        """
        Verify CTO signature on transaction
        
        In production, this would use real cryptographic verification
        For now, we simulate with hash matching
        """
        # Create hash of transaction data
        data_str = json.dumps(transaction_data, sort_keys=True)
        expected_hash = hashlib.sha256(
            f"{data_str}{self.cto_public_key}".encode()
        ).hexdigest()
        
        # In production: verify signature with public key
        # For now: check if signature matches expected hash
        return signature == expected_hash
    
    def create_signature(self, transaction_data: Dict[str, Any]) -> str:
        """Create CTO signature (for testing)"""
        data_str = json.dumps(transaction_data, sort_keys=True)
        return hashlib.sha256(
            f"{data_str}{self.cto_public_key}".encode()
        ).hexdigest()


class JuryEntropyChecker:
    """Checks Jury verdict and Entropy score"""
    
    def __init__(self, jury_client, entropy_monitor):
        self.jury_client = jury_client
        self.entropy_monitor = entropy_monitor
    
    def check_jury_entropy(
        self,
        agent_id: str,
        action: str,
        payload: Dict[str, Any]
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check both Jury verdict and Entropy score
        
        Returns:
            (passed, details)
        """
        # Check Jury
        jury_passed, jury_err = self.jury_client.EvaluateAction(
            None,  # context
            agent_id,
            action,
            payload
        )
        
        # Check Entropy
        entropy_passed, entropy_err = self.entropy_monitor.CheckEntropy(
            None,  # context
            json.dumps(payload).encode(),
            agent_id
        )
        
        passed = jury_passed and entropy_passed
        
        details = {
            "jury_passed": jury_passed,
            "jury_error": str(jury_err) if jury_err else None,
            "entropy_passed": entropy_passed,
            "entropy_error": str(entropy_err) if entropy_err else None
        }
        
        return passed, details


# Integration with Policy Enforcement
def enforce_with_signals(
    transaction_id: str,
    required_signals: List[str],
    signal_collector: SignalCollector
) -> tuple[bool, str]:
    """
    Enforce policy with required signals
    
    Returns:
        (is_allowed, action)
    """
    all_valid, missing = signal_collector.verify_signals(
        transaction_id,
        required_signals
    )
    
    if not all_valid:
        return False, f"BLOCK: Missing signals: {', '.join(missing)}"
    
    return True, "ALLOW"


# Example usage
if __name__ == "__main__":
    # Create signal collector
    collector = SignalCollector()
    
    # Transaction requires CTO signature and Jury+Entropy check
    tx_id = "tx-12345"
    required = ["CTO_SIGNATURE", "JURY_ENTROPY_CHECK"]
    
    # Add CTO signature
    cto_verifier = CTOSignatureVerifier("cto_public_key_abc123")
    tx_data = {"amount": 10000, "vendor": "ACME Corp"}
    signature = cto_verifier.create_signature(tx_data)
    
    collector.add_signal(
        transaction_id=tx_id,
        signal_type=SignalType.CTO_SIGNATURE,
        value=signature,
        ttl_seconds=300,  # 5 minutes
        metadata={"signer": "CTO", "transaction": tx_data}
    )
    
    # Add Jury+Entropy check (simulated)
    collector.add_signal(
        transaction_id=tx_id,
        signal_type=SignalType.JURY_ENTROPY_CHECK,
        value={"jury_passed": True, "entropy_passed": True},
        ttl_seconds=60,  # 1 minute
        metadata={"jury_score": 0.95, "entropy_score": 2.3}
    )
    
    # Verify signals
    is_allowed, action = enforce_with_signals(tx_id, required, collector)
    print(f"Transaction allowed: {is_allowed}, action: {action}")
    
    # Get all signals
    signals = collector.get_signals(tx_id)
    print(f"Signals collected: {len(signals)}")
    for signal in signals:
        print(f"  - {signal.signal_type.value}: {signal.value}")
