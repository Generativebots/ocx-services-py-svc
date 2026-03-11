"""
OCX Platform Config Store (Python)
===================================

Reads platform-level configuration from the `platform_config` Supabase table.

⚠️  THE DATABASE (platform_config table + seed data) IS THE SOURCE OF TRUTH.
    Code-level fallbacks are EMERGENCY-ONLY for catastrophic DB failure.
    Per-tenant overrides go into platform_config with a non-null tenant_id.

Lookup order:
    1. Tenant-specific override (platform_config WHERE tenant_id = X)
    2. Platform default (platform_config WHERE tenant_id IS NULL)
    3. Caller-supplied default (emergency only)

Usage:
    from config.platform_config_store import get_platform_value

    # Reads tenant override → platform default → caller fallback
    base_cost = get_platform_value("pricing", "base_transaction_cost",
                                   tenant_id="abc-123", default=0.001)
"""

import os
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class EmptyTenantIDError(ValueError):
    """Raised when tenant_id is blank or whitespace-only."""
    pass


def validate_tenant_id(tenant_id: str) -> None:
    """Validate that tenant_id is non-empty. All APIs require a valid tenant from login context."""
    if not tenant_id or not tenant_id.strip():
        raise EmptyTenantIDError(
            "tenant_id is required — it must come from the authenticated login context"
        )

# ============================================================================
# CACHE
# ============================================================================

_cache: Dict[str, Any] = {}
_cache_expiry: Dict[str, datetime] = {}
_CACHE_TTL = timedelta(minutes=5)


def _get_supabase_client():
    """Lazy-load Supabase client."""
    try:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return None
        from supabase import create_client
        return create_client(url, key)
    except Exception as e:
        logger.warning(f"Failed to create Supabase client for platform config: {e}")
        return None


def _load_from_db(tenant_id: str, category: str, key: str) -> Optional[Any]:
    """Load a value from the platform_config table."""
    client = _get_supabase_client()
    if client is None:
        return None

    try:
        query = (
            client.table("platform_config")
            .select("value")
            .eq("category", category)
            .eq("key", key)
        )
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        else:
            query = query.is_("tenant_id", "null")

        response = query.execute()
        if response.data:
            raw_value = response.data[0].get("value")
            if isinstance(raw_value, dict) and "v" in raw_value:
                return raw_value["v"]
            return raw_value
    except Exception as e:
        logger.warning(f"Failed to load platform config {category}:{key}: {e}")

    return None


def get_platform_value(
    category: str,
    key: str,
    *,
    tenant_id: str,
    default: Any = None,
) -> Any:
    """
    Get a platform config value from the DB.

    Lookup order:
    1. Tenant-specific override (platform_config WHERE tenant_id = X)
    2. Platform default (platform_config WHERE tenant_id IS NULL)
    3. Caller-supplied default (emergency fallback only)

    The DB seed data (002_seed_platform_config.sql) is the source of truth.
    The `default` parameter is ONLY used if the DB is unreachable.

    Args:
        category: Config category (e.g., "pricing", "trust", "jury")
        key: Config key (e.g., "base_transaction_cost")
        tenant_id: Tenant ID — REQUIRED, must come from login context
        default: Emergency fallback if DB is unreachable

    Returns:
        The config value

    Raises:
        EmptyTenantIDError: if tenant_id is empty or whitespace-only
    """
    validate_tenant_id(tenant_id)

    # 1. Tenant override
    if tenant_id:
        cache_key = f"{tenant_id}:{category}:{key}"
        if cache_key in _cache and datetime.now(timezone.utc) < _cache_expiry.get(cache_key, datetime.min):
            return _cache[cache_key]

        val = _load_from_db(tenant_id, category, key)
        if val is not None:
            _cache[cache_key] = val
            _cache_expiry[cache_key] = datetime.now(timezone.utc) + _CACHE_TTL
            return val

    # 2. Platform default (from DB seed data)
    default_cache_key = f":{category}:{key}"
    if default_cache_key in _cache and datetime.now(timezone.utc) < _cache_expiry.get(default_cache_key, datetime.min):
        return _cache[default_cache_key]

    val = _load_from_db("", category, key)
    if val is not None:
        _cache[default_cache_key] = val
        _cache_expiry[default_cache_key] = datetime.now(timezone.utc) + _CACHE_TTL
        return val

    # 3. Emergency fallback — DB was unreachable
    if default is not None:
        logger.warning(
            f"DB unreachable for {category}:{key}, using emergency fallback: {default}"
        )
    return default


def invalidate_tenant(tenant_id: str) -> None:
    """Invalidate all cached values for a tenant."""
    keys_to_remove = [k for k in _cache if k.startswith(f"{tenant_id}:")]
    for k in keys_to_remove:
        _cache.pop(k, None)
        _cache_expiry.pop(k, None)
    logger.info(f"Platform config cache invalidated for tenant: {tenant_id}")


def invalidate_all() -> None:
    """Clear entire platform config cache."""
    _cache.clear()
    _cache_expiry.clear()
    logger.info("Platform config cache fully invalidated")


def get_platform_default(
    category: str,
    key: str,
    *,
    default: Any = None,
) -> Any:
    """
    Get a platform default (tenant_id IS NULL) without requiring a tenant context.

    Use for infrastructure config at startup before any tenant has logged in.
    For request-time reads, use get_platform_value() with a valid tenant_id.

    Lookup order:
    1. Platform default (platform_config WHERE tenant_id IS NULL)
    2. Caller-supplied default (emergency fallback only)

    Args:
        category: Config category (e.g., "scanner", "impact")
        key: Config key (e.g., "severity_high_weight")
        default: Emergency fallback if DB is unreachable

    Returns:
        The config value
    """
    cache_key = f":{category}:{key}"
    if cache_key in _cache and datetime.now(timezone.utc) < _cache_expiry.get(cache_key, datetime.min):
        return _cache[cache_key]

    val = _load_from_db("", category, key)
    if val is not None:
        _cache[cache_key] = val
        _cache_expiry[cache_key] = datetime.now(timezone.utc) + _CACHE_TTL
        return val

    if default is not None:
        logger.warning(
            f"DB unreachable for platform default {category}:{key}, using fallback: {default}"
        )
    return default
