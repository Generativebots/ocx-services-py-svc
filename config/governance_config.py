"""
OCX Governance Configuration Loader
====================================

Loads tenant-specific governance parameters from the `tenant_governance_config`
Supabase table, caching per-tenant with fallback to recommended defaults.

Usage:
    from config.governance_config import get_tenant_governance_config

    cfg = get_tenant_governance_config(tenant_id="abc-123")
    threshold = cfg["jury_trust_threshold"]  # 0.65
"""

import os
import logging
from typing import Dict, Any, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# ============================================================================
# DEFAULT VALUES — mirror the Go DefaultConfig() and Supabase table defaults
# ============================================================================

DEFAULT_GOVERNANCE_CONFIG: Dict[str, Any] = {
    # Trust Thresholds & Scores
    "jury_trust_threshold": 0.65,
    "jury_audit_weight": 0.40,
    "jury_reputation_weight": 0.30,
    "jury_attestation_weight": 0.20,
    "jury_history_weight": 0.10,
    "new_agent_default_score": 0.30,
    "min_balance_threshold": 0.20,
    "quarantine_score": 0.00,
    "point_to_score_factor": 0.01,
    "kill_switch_threshold": 0.30,
    "quorum_threshold": 0.66,

    # Tax & Economics
    "trust_tax_base_rate": 0.10,
    "federation_tax_base_rate": 0.10,
    "per_event_tax_rate": 0.01,
    "marketplace_commission": 0.30,
    "hitl_cost_multiplier": 10.0,

    # Risk & Metering
    "risk_multipliers": {
        "data_query": 1.0, "read_only": 0.5, "file_read": 1.0,
        "file_write": 3.0, "network_call": 2.0, "api_call": 2.5,
        "data_mutation": 4.0, "admin_action": 5.0, "exec_command": 5.0,
        "payment": 4.0, "pii_access": 3.5, "unknown": 2.0,
    },
    "meter_high_trust_threshold": 0.80,
    "meter_high_trust_discount": 0.70,
    "meter_med_trust_threshold": 0.60,
    "meter_med_trust_discount": 0.85,
    "meter_low_trust_threshold": 0.30,
    "meter_low_trust_surcharge": 1.50,
    "meter_base_cost_per_frame": 0.001,
    "unknown_tool_min_reputation": 0.95,
    "unknown_tool_tax_coefficient": 5.0,

    # Tri-Factor Gate
    "identity_threshold": 0.65,
    "entropy_threshold": 7.5,
    "jitter_threshold": 0.01,
    "cognitive_threshold": 0.65,
    "entropy_high_cap": 4.8,
    "entropy_encrypted_threshold": 7.5,
    "entropy_suspicious_threshold": 6.0,

    # Security
    "drift_threshold": 0.20,
    "anomaly_threshold": 5,

    # Federation Trust Decay
    "decay_half_life_hours": 168,
    "trust_ema_alpha": 0.3,
    "failure_penalty_factor": 0.8,
    "supermajority_threshold": 0.75,
    "handshake_min_trust": 0.50,
}


# Per-tenant cache
_tenant_config_cache: Dict[str, Dict[str, Any]] = {}


def _get_supabase_client():
    """Lazy-load Supabase client to avoid circular imports."""
    try:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return None
        from supabase import create_client
        return create_client(url, key)
    except Exception as e:
        logger.warning(f"Failed to create Supabase client for governance config: {e}")
        return None


def _load_from_supabase(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Load governance config for a tenant from Supabase."""
    client = _get_supabase_client()
    if client is None:
        return None

    try:
        response = (
            client.table("tenant_governance_config")
            .select("*")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        if response.data:
            return response.data[0]
    except Exception as e:
        logger.warning(f"Failed to load governance config for tenant {tenant_id}: {e}")

    return None


def get_tenant_governance_config(tenant_id: str) -> Dict[str, Any]:
    """
    Get governance config for a tenant.

    Lookup order:
    1. In-memory cache
    2. Supabase tenant_governance_config table
    3. Hardcoded defaults (fail-safe)

    Args:
        tenant_id: The tenant UUID

    Returns:
        Dict with governance parameters
    """
    # 1. Cache hit
    if tenant_id in _tenant_config_cache:
        return _tenant_config_cache[tenant_id]

    # 2. Load from Supabase
    config = _load_from_supabase(tenant_id)
    if config is not None:
        # Merge with defaults for any missing keys
        merged = {**DEFAULT_GOVERNANCE_CONFIG, **config}
        _tenant_config_cache[tenant_id] = merged
        logger.info(f"Loaded governance config for tenant {tenant_id} from Supabase")
        return merged

    # 3. Fall back to defaults
    logger.info(f"Using default governance config for tenant {tenant_id}")
    _tenant_config_cache[tenant_id] = DEFAULT_GOVERNANCE_CONFIG.copy()
    return _tenant_config_cache[tenant_id]


def invalidate_tenant_config(tenant_id: str) -> None:
    """Invalidate cached config for a tenant (call after config update)."""
    _tenant_config_cache.pop(tenant_id, None)
    logger.info(f"Governance config cache invalidated for tenant {tenant_id}")


def invalidate_all_config() -> None:
    """Clear entire governance config cache."""
    _tenant_config_cache.clear()
