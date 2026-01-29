"""
OCX Trust Calculation Service (The Jury)
Implements the weighted trust formula from the OCX patent:
trust_level = (0.40 × audit) + (0.30 × reputation) + (0.20 × attestation) + (0.10 × history)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Optional, AsyncIterator
import grpc
from grpc import aio

# Import generated protobuf (would be generated from .proto files)
# import traffic_assessment_pb2
# import traffic_assessment_pb2_grpc

# For now, we'll define the structure
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
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
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
            (scores.audit * WEIGHT_AUDIT) +
            (scores.reputation * WEIGHT_REPUTATION) +
            (scores.attestation * WEIGHT_ATTESTATION) +
            (scores.history * WEIGHT_HISTORY)
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
        tax_amount = trust_deficit * TRUST_TAX_RATE * transaction_value
        
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
            "audit_weighted": scores.audit * WEIGHT_AUDIT,
            "reputation_weighted": scores.reputation * WEIGHT_REPUTATION,
            "attestation_weighted": scores.attestation * WEIGHT_ATTESTATION,
            "history_weighted": scores.history * WEIGHT_HISTORY,
            "trust_level": trust_level,
            "weight_audit": WEIGHT_AUDIT,
            "weight_reputation": WEIGHT_REPUTATION,
            "weight_attestation": WEIGHT_ATTESTATION,
            "weight_history": WEIGHT_HISTORY,
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
        if trust_level >= TRUST_THRESHOLD:
            action = VerdictAction.ACTION_ALLOW.name
            reasoning = f"Trust level {trust_level:.3f} meets threshold {TRUST_THRESHOLD}"
        elif trust_level >= 0.3:
            action = VerdictAction.ACTION_HOLD.name
            reasoning = f"Trust level {trust_level:.3f} requires verification (threshold {TRUST_THRESHOLD})"
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
# IDENTITY DATABASE (Mock - would be Redis/Spanner in production)
# ============================================================================

class IdentityDatabase:
    """
    Mock identity database for storing and retrieving entity scores.
    In production, this would be backed by Redis or Cloud Spanner.
    """
    
    def __init__(self):
        self.identities: Dict[str, EntityScores] = {}
        self.logger = logging.getLogger(__name__)
        
        # Seed with some test data
        self._seed_test_data()
    
    def _seed_test_data(self):
        """Seed database with test identities"""
        self.identities = {
            # High trust agent
            "sha256:abc123": EntityScores(
                audit=0.95,
                reputation=0.90,
                attestation=0.85,
                history=0.80
            ),
            # Medium trust agent
            "sha256:def456": EntityScores(
                audit=0.70,
                reputation=0.65,
                attestation=0.60,
                history=0.50
            ),
            # Low trust agent
            "sha256:xyz789": EntityScores(
                audit=0.30,
                reputation=0.25,
                attestation=0.20,
                history=0.10
            ),
        }
    
    async def get_scores(self, binary_hash: str) -> EntityScores:
        """
        Retrieve entity scores by binary hash.
        
        Args:
            binary_hash: SHA-256 hash of the binary
            
        Returns:
            EntityScores or default neutral scores
        """
        scores = self.identities.get(binary_hash)
        
        if scores is None:
            # Default neutral scores for unknown entities
            self.logger.warning(f"Unknown binary hash: {binary_hash}, using defaults")
            scores = EntityScores(
                audit=0.5,
                reputation=0.5,
                attestation=0.5,
                history=0.0  # New entity has no history
            )
        
        return scores
    
    async def update_scores(self, binary_hash: str, scores: EntityScores):
        """Update scores for an entity"""
        self.identities[binary_hash] = scores
        self.logger.info(f"Updated scores for {binary_hash}")


# ============================================================================
# GRPC SERVICE IMPLEMENTATION
# ============================================================================

class TrustCalculationService:
    """
    gRPC service that receives traffic events from Go Interceptor
    and returns trust verdicts.
    
    This is the "Jury" that makes real-time trust decisions.
    """
    
    def __init__(self):
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
                
                # 5. Create response (would use protobuf in production)
                response = {
                    "request_id": request.request_id,
                    "verdict": {
                        "action": result.action,
                        "trust_level": result.trust_level,
                        "trust_tax": result.trust_tax,
                    },
                    "confidence_score": result.trust_level,
                    "reasoning": result.reasoning,
                    "metadata": {
                        "binary_path": binary_path,
                        "pid": pid,
                        "breakdown": result.breakdown,
                    }
                }
                
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

async def serve(port: int = None):
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
    
    # Add service
    service = TrustCalculationService()
    # traffic_assessment_pb2_grpc.add_TrafficAssessorServicer_to_server(service, server)
    
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
