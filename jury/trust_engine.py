"""
OCX Trust Calculation Service (The Jury)
Implements the weighted trust formula from the OCX patent:
trust_level = (0.40 × audit) + (0.30 × reputation) + (0.20 × attestation) + (0.10 × history)

C1+C2 FIX: Now imports proto stubs and registers gRPC service properly.
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from typing import Dict, Optional, AsyncIterator
import grpc
from grpc import aio

# C1+C2 FIX: Import generated protobuf stubs (no longer commented out)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proto import traffic_assessment_pb2
from proto import traffic_assessment_pb2_grpc

from enum import Enum

# ============================================================================
# CONSTANTS - OCX Protocol Weights
# ============================================================================

WEIGHT_AUDIT = 0.40        # 40% - Binary audit/provenance verification
WEIGHT_REPUTATION = 0.30   # 30% - Historical interaction success rate
WEIGHT_ATTESTATION = 0.20  # 20% - Fresh cryptographic attestation
WEIGHT_HISTORY = 0.10      # 10% - Relationship age and depth

TRUST_THRESHOLD = 0.65     # Minimum trust for ACTION_ALLOW
TRUST_TAX_RATE = 0.10      # 10% base tax rate

# Governance config loader — tenant-specific overrides
try:
    from config.governance_config import get_tenant_governance_config
    _HAS_GOV_CONFIG = True
except ImportError:
    _HAS_GOV_CONFIG = False


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class EntityScores:
    """Individual components of trust calculation"""
    audit: float        # 0.0 to 1.0 - Binary hash verification
    reputation: float   # 0.0 to 1.0 - Success rate
    attestation: float  # 0.0 to 1.0 - Fresh attestation
    history: float      # 0.0 to 1.0 - Relationship depth


@dataclass
class TrustResult:
    """Result of trust calculation"""
    trust_level: float
    trust_tax: float
    action: str  # ALLOW, BLOCK, HOLD
    reasoning: str
    breakdown: Dict[str, float]


class VerdictAction(Enum):
    """Verdict actions matching protobuf"""
    ACTION_ALLOW = 0
    ACTION_BLOCK = 1
    ACTION_HOLD = 2


# ============================================================================
# TRUST CALCULATION ENGINE
# ============================================================================

class TrustCalculationEngine:
    """
    Core engine implementing the OCX weighted trust formula.
    This is the mathematical heart of the Jury.
    """
    
    def __init__(self, tenant_id: str = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.tenant_id = tenant_id
        
        # Load weights from governance config if available
        if tenant_id and _HAS_GOV_CONFIG:
            cfg = get_tenant_governance_config(tenant_id)
            self.weight_audit = cfg.get("jury_audit_weight", WEIGHT_AUDIT)
            self.weight_reputation = cfg.get("jury_reputation_weight", WEIGHT_REPUTATION)
            self.weight_attestation = cfg.get("jury_attestation_weight", WEIGHT_ATTESTATION)
            self.weight_history = cfg.get("jury_history_weight", WEIGHT_HISTORY)
            self.trust_threshold = cfg.get("jury_trust_threshold", TRUST_THRESHOLD)
            self.trust_tax_rate = cfg.get("trust_tax_base_rate", TRUST_TAX_RATE)
        else:
            self.weight_audit = WEIGHT_AUDIT
            self.weight_reputation = WEIGHT_REPUTATION
            self.weight_attestation = WEIGHT_ATTESTATION
            self.weight_history = WEIGHT_HISTORY
            self.trust_threshold = TRUST_THRESHOLD
            self.trust_tax_rate = TRUST_TAX_RATE
    async def calculate_trust(self, scores: EntityScores) -> float:
        """
        Implements the Weighted Trust Calculation from the OCX Patent.
        
        Formula:
        trust_level = (0.40 × audit_score) + 
                     (0.30 × reputation_score) + 
                     (0.20 × attestation_score) + 
                     (0.10 × history_score)
        
        Args:
            scores: EntityScores with all four components
            
        Returns:
            float: Trust level between 0.0 and 1.0
        """
        trust_level = (
            (scores.audit * self.weight_audit) +
            (scores.reputation * self.weight_reputation) +
            (scores.attestation * self.weight_attestation) +
            (scores.history * self.weight_history)
        )
        
        # Ensure bounds
        trust_level = max(0.0, min(1.0, trust_level))
        
        self.logger.debug(
            f"Trust calculated: {trust_level:.3f} "
            f"(A:{scores.audit:.2f} R:{scores.reputation:.2f} "
            f"At:{scores.attestation:.2f} H:{scores.history:.2f})"
        )
        
        return trust_level
    
    def calculate_trust_tax(self, trust_level: float, transaction_value: float = 1000.0) -> float:
        """
        Calculate the Trust Tax based on trust deficit.
        
        Formula:
        trust_tax = (1.0 - trust_level) × base_tax_rate × transaction_value
        
        Examples:
        - Trust 1.0 → Tax 0% (perfect trust)
        - Trust 0.85 → Tax 1.5%
        - Trust 0.5 → Tax 5%
        - Trust 0.0 → Tax 10%
        
        Args:
            trust_level: Calculated trust level (0.0 to 1.0)
            transaction_value: Value of the transaction
            
        Returns:
            float: Tax amount to be collected
        """
        trust_deficit = 1.0 - trust_level
        tax_amount = trust_deficit * self.trust_tax_rate * transaction_value
        
        return tax_amount
    
    def get_trust_breakdown(self, scores: EntityScores, trust_level: float) -> Dict[str, float]:
        """
        Get detailed breakdown of trust components.
        
        Returns:
            Dict with weighted contributions
        """
        return {
            "audit_score": scores.audit,
            "reputation_score": scores.reputation,
            "attestation_score": scores.attestation,
            "history_score": scores.history,
            "audit_weighted": scores.audit * self.weight_audit,
            "reputation_weighted": scores.reputation * self.weight_reputation,
            "attestation_weighted": scores.attestation * self.weight_attestation,
            "history_weighted": scores.history * self.weight_history,
            "trust_level": trust_level,
            "weight_audit": self.weight_audit,
            "weight_reputation": self.weight_reputation,
            "weight_attestation": self.weight_attestation,
            "weight_history": self.weight_history,
        }
    
    async def assess_and_decide(
        self,
        scores: EntityScores,
        transaction_value: float = 1000.0
    ) -> TrustResult:
        """
        Complete assessment: calculate trust, determine action, calculate tax.
        
        Args:
            scores: Entity trust scores
            transaction_value: Transaction value for tax calculation
            
        Returns:
            TrustResult with verdict and tax
        """
        # 1. Calculate trust level
        trust_level = await self.calculate_trust(scores)
        
        # 2. Calculate trust tax
        trust_tax = self.calculate_trust_tax(trust_level, transaction_value)
        
        # 3. Determine action
        if trust_level >= self.trust_threshold:
            action = VerdictAction.ACTION_ALLOW.name
            reasoning = f"Trust level {trust_level:.3f} meets threshold {self.trust_threshold}"
        elif trust_level >= 0.3:
            action = VerdictAction.ACTION_HOLD.name
            reasoning = f"Trust level {trust_level:.3f} requires verification (threshold {self.trust_threshold})"
        else:
            action = VerdictAction.ACTION_BLOCK.name
            reasoning = f"Trust level {trust_level:.3f} below minimum threshold"
        
        # 4. Get breakdown
        breakdown = self.get_trust_breakdown(scores, trust_level)
        
        return TrustResult(
            trust_level=trust_level,
            trust_tax=trust_tax,
            action=action,
            reasoning=reasoning,
            breakdown=breakdown
        )


# ============================================================================
# IDENTITY DATABASE — Supabase-backed entity trust scores
# ============================================================================

class IdentityDatabase:
    """
    Identity database for storing and retrieving entity trust scores.
    Queries the `agents` table in Supabase for real trust data.
    Falls back to neutral defaults for unknown entities.
    """
    
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self._cache: Dict[str, EntityScores] = {}
        self._supabase_url = os.getenv("SUPABASE_URL", "")
        self._supabase_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    
    async def get_scores(self, binary_hash: str) -> EntityScores:
        """
        Retrieve entity scores by binary hash / agent ID.
        Queries Supabase agents table, falls back to neutral scores.
        """
        # Check local cache first
        if binary_hash in self._cache:
            return self._cache[binary_hash]
        
        # Query Supabase for agent trust data
        if self._supabase_url and self._supabase_key:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(
                        f"{self._supabase_url}/rest/v1/agents",
                        params={
                            "or": f"(agent_id.eq.{binary_hash},binary_hash.eq.{binary_hash})",
                            "select": "trust_score,reputation_score,attestation_valid,interaction_count",
                            "limit": "1",
                        },
                        headers={
                            "apikey": self._supabase_key,
                            "Authorization": f"Bearer {self._supabase_key}",
                        },
                    )
                    if resp.status_code == 200:
                        rows = resp.json()
                        if rows:
                            row = rows[0]
                            scores = EntityScores(
                                audit=float(row.get("trust_score", 0.5)),
                                reputation=float(row.get("reputation_score", 0.5)),
                                attestation=1.0 if row.get("attestation_valid", False) else 0.3,
                                history=min(1.0, float(row.get("interaction_count", 0)) / 100.0),
                            )
                            self._cache[binary_hash] = scores
                            return scores
            except Exception as e:
                self.logger.warning(f"Failed to query Supabase for scores: {e}")
        
        # Neutral defaults for unknown entities
        self.logger.warning(f"Unknown entity: {binary_hash}, using neutral defaults")
        scores = EntityScores(
            audit=0.5,
            reputation=0.5,
            attestation=0.5,
            history=0.0  # New entity has no history
        )
        return scores
    
    async def update_scores(self, binary_hash: str, scores: EntityScores) -> None:
        """Update scores for an entity (cache + DB)."""
        self._cache[binary_hash] = scores
        
        if self._supabase_url and self._supabase_key:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=3.0) as client:
                    await client.patch(
                        f"{self._supabase_url}/rest/v1/agents",
                        params={"agent_id": f"eq.{binary_hash}"},
                        json={
                            "trust_score": scores.audit,
                            "reputation_score": scores.reputation,
                        },
                        headers={
                            "apikey": self._supabase_key,
                            "Authorization": f"Bearer {self._supabase_key}",
                            "Content-Type": "application/json",
                            "Prefer": "return=minimal",
                        },
                    )
            except Exception as e:
                self.logger.warning(f"Failed to persist scores to Supabase: {e}")
        
        self.logger.info(f"Updated scores for {binary_hash}")


# ============================================================================
# GRPC SERVICE IMPLEMENTATION
# ============================================================================

class TrustCalculationService(traffic_assessment_pb2_grpc.TrafficAssessorServicer):
    """
    gRPC service that receives traffic events from Go Interceptor
    and returns trust verdicts.

    C1+C2 FIX: Now inherits from TrafficAssessorServicer so gRPC
    dispatches InspectTraffic calls to this service.

    This is the "Jury" that makes real-time trust decisions.
    """

    def __init__(self) -> None:
        self.engine = TrustCalculationEngine()
        self.identity_db = IdentityDatabase()
        self.logger = logging.getLogger(__name__)

        # Metrics
        self.total_assessments = 0
        self.blocked_count = 0
        self.allowed_count = 0
        self.held_count = 0
    
    async def InspectTraffic(
        self,
        request_iterator: AsyncIterator,
        context: grpc.aio.ServicerContext
    ) -> AsyncIterator:
        """
        Bidirectional streaming RPC for real-time traffic assessment.
        
        Flow:
        1. Receive traffic event from Go Interceptor
        2. Look up entity scores by binary hash
        3. Calculate weighted trust
        4. Determine verdict (ALLOW/BLOCK/HOLD)
        5. Calculate trust tax
        6. Stream verdict back to Go for kernel enforcement
        
        Args:
            request_iterator: Stream of TrafficEvent from Go
            context: gRPC context
            
        Yields:
            AssessmentResponse with verdict and trust metrics
        """
        self.logger.info("🎯 Jury session started")
        
        try:
            async for request in request_iterator:
                self.total_assessments += 1
                
                # Extract metadata
                pid = request.metadata.pid
                binary_hash = request.metadata.binary_sha256
                binary_path = request.metadata.binary_path
                transaction_value = request.metadata.get("transaction_value", 1000.0)
                
                self.logger.info(
                    f"📨 Assessment request: PID={pid} "
                    f"Hash={binary_hash[:16]}... Path={binary_path}"
                )
                
                # 1. Retrieve entity scores
                scores = await self.identity_db.get_scores(binary_hash)
                
                # 2. Perform trust assessment
                result = await self.engine.assess_and_decide(scores, transaction_value)
                
                # 3. Update metrics
                if result.action == VerdictAction.ACTION_ALLOW.name:
                    self.allowed_count += 1
                elif result.action == VerdictAction.ACTION_BLOCK.name:
                    self.blocked_count += 1
                else:
                    self.held_count += 1
                
                # 4. Log decision
                self.logger.info(
                    f"⚖️  Verdict: {result.action} | "
                    f"Trust: {result.trust_level:.3f} | "
                    f"Tax: ${result.trust_tax:.2f} | "
                    f"Reason: {result.reasoning}"
                )
                
                # 5. Create proto response (C1+C2 FIX: proper proto objects)
                action_map = {
                    VerdictAction.ACTION_ALLOW.name: traffic_assessment_pb2.VerdictAction.ACTION_ALLOW,
                    VerdictAction.ACTION_BLOCK.name: traffic_assessment_pb2.VerdictAction.ACTION_BLOCK,
                    VerdictAction.ACTION_HOLD.name: traffic_assessment_pb2.VerdictAction.ACTION_BLOCK,  # HOLD maps to BLOCK in proto
                }
                verdict = traffic_assessment_pb2.Verdict(
                    action=action_map.get(result.action, traffic_assessment_pb2.VerdictAction.ACTION_BLOCK)
                )
                response = traffic_assessment_pb2.AssessmentResponse(
                    request_id=request.request_id,
                    verdict=verdict,
                    confidence_score=result.trust_level,
                    reasoning=result.reasoning,
                    metadata={
                        "trust_level": str(result.trust_level),
                        "trust_tax": str(result.trust_tax),
                        "binary_path": binary_path,
                        "pid": str(pid),
                    }
                )

                # 6. Stream response back to Go Interceptor
                yield response
        
        except Exception as e:
            self.logger.error(f"❌ Error in InspectTraffic: {e}", exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
        
        finally:
            self.logger.info(
                f"📊 Session ended: {self.total_assessments} assessments | "
                f"Allowed: {self.allowed_count} | "
                f"Blocked: {self.blocked_count} | "
                f"Held: {self.held_count}"
            )
    
    def get_metrics(self) -> Dict[str, int]:
        """Get service metrics"""
        return {
            "total_assessments": self.total_assessments,
            "allowed_count": self.allowed_count,
            "blocked_count": self.blocked_count,
            "held_count": self.held_count,
            "block_rate": self.blocked_count / max(1, self.total_assessments),
        }


# ============================================================================
# SERVER SETUP
# ============================================================================

async def serve(port: int = None) -> None:
    """
    Start the Trust Calculation Service (Jury) gRPC server.
    
    Args:
        port: Port to listen on (default: from PORT env var or 50051)
    """
    # Get port from environment (Cloud Run requirement)
    if port is None:
        port = int(os.getenv("PORT", "50051"))
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    # Create gRPC server
    server = aio.server()
    
    # C1+C2 FIX: Service registration is no longer commented out
    service = TrustCalculationService()
    traffic_assessment_pb2_grpc.add_TrafficAssessorServicer_to_server(service, server)
    
    # Listen on port
    server.add_insecure_port(f'[::]:{port}')
    
    logger.info(f"🚀 OCX Trust Calculation Service (Jury) starting on port {port}")
    logger.info(f"📐 Using weighted trust formula:")
    logger.info(f"   - Audit: {WEIGHT_AUDIT * 100}%")
    logger.info(f"   - Reputation: {WEIGHT_REPUTATION * 100}%")
    logger.info(f"   - Attestation: {WEIGHT_ATTESTATION * 100}%")
    logger.info(f"   - History: {WEIGHT_HISTORY * 100}%")
    logger.info(f"🎯 Trust threshold: {TRUST_THRESHOLD}")
    logger.info(f"💰 Trust tax rate: {TRUST_TAX_RATE * 100}%")
    
    await server.start()
    logger.info("✅ Server started successfully")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down gracefully...")
        await server.stop(grace=5)
        logger.info("👋 Server stopped")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    asyncio.run(serve())
