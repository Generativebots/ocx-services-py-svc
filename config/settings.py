"""
OCX Python Services - Centralized Configuration
================================================

Usage:
    from config.settings import config
    
    # Access settings
    db_url = config.database.supabase_url
    redis_host = config.cache.redis_host
    
Environment overrides:
    All settings can be overridden via environment variables.
    Environment variables take precedence over config file values.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from functools import lru_cache


@dataclass
class ServerConfig:
    """Server configuration"""
    port: int = int(os.getenv("PORT", "8000"))
    host: str = os.getenv("HOST", "0.0.0.0")
    env: str = os.getenv("OCX_ENV", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    workers: int = int(os.getenv("WORKERS", "4"))


@dataclass
class DatabaseConfig:
    """Database configuration (Supabase + PostgreSQL)"""
    # Supabase
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    
    # PostgreSQL Direct (fallback)
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "ocx")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    postgres_ssl_mode: str = os.getenv("POSTGRES_SSL_MODE", "prefer")
    
    # Connection pool
    pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))
    pool_timeout: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    
    # Backend selection
    backend: str = os.getenv("DB_BACKEND", "supabase")  # supabase, postgresql, spanner


@dataclass
class CacheConfig:
    """Redis cache configuration"""
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "")
    redis_db: int = int(os.getenv("REDIS_DB", "0"))
    ttl_seconds: int = int(os.getenv("CACHE_TTL", "3600"))


@dataclass  
class AIModelsConfig:
    """AI/LLM configuration"""
    # vLLM (self-hosted)
    vllm_enabled: bool = os.getenv("VLLM_ENABLED", "true").lower() == "true"
    vllm_base_url: str = os.getenv("VLLM_BASE_URL", "http://localhost:8000")
    vllm_model: str = os.getenv("VLLM_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")
    vllm_api_key: str = os.getenv("VLLM_API_KEY", "EMPTY")
    
    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
    
    # Google AI
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    google_model: str = os.getenv("GOOGLE_MODEL", "gemini-2.0-pro")
    
    # Anthropic
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-opus")
    
    # Fallback priority
    model_priority: List[str] = field(default_factory=lambda: 
        os.getenv("MODEL_PRIORITY", "vllm,openai,google,anthropic").split(","))


@dataclass
class TrustConfig:
    """Trust calculation configuration"""
    # Tri-Factor Gate weights
    audit_weight: float = float(os.getenv("TRUST_WEIGHT_AUDIT", "0.4"))
    reputation_weight: float = float(os.getenv("TRUST_WEIGHT_REPUTATION", "0.3"))
    attestation_weight: float = float(os.getenv("TRUST_WEIGHT_ATTESTATION", "0.2"))
    history_weight: float = float(os.getenv("TRUST_WEIGHT_HISTORY", "0.1"))
    
    # Thresholds
    min_trust_score: float = float(os.getenv("MIN_TRUST_SCORE", "0.3"))
    quarantine_threshold: float = float(os.getenv("QUARANTINE_THRESHOLD", "0.2"))
    
    # Session
    session_expiry_minutes: int = int(os.getenv("SESSION_EXPIRY_MINUTES", "5"))


@dataclass
class GovernanceConfig:
    """Governance configuration"""
    committee_size: int = int(os.getenv("COMMITTEE_SIZE", "22"))
    quorum_percentage: float = float(os.getenv("QUORUM_PERCENTAGE", "0.67"))
    voting_period_hours: int = int(os.getenv("VOTING_PERIOD_HOURS", "168"))


@dataclass
class MonitoringConfig:
    """Monitoring and observability"""
    entropy_threshold: float = float(os.getenv("ENTROPY_THRESHOLD", "0.85"))
    latency_alert_ms: int = int(os.getenv("LATENCY_ALERT_MS", "200"))
    enable_live_stream: bool = os.getenv("ENABLE_LIVE_STREAM", "true").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


@dataclass
class SpannerConfig:
    """Google Cloud Spanner configuration (for enterprise tier)"""
    project_id: str = os.getenv("SPANNER_PROJECT_ID", "")
    instance_id: str = os.getenv("SPANNER_INSTANCE_ID", "")
    database_id: str = os.getenv("SPANNER_DATABASE_ID", "")


@dataclass
class ServiceURLsConfig:
    """Internal service URLs"""
    trust_registry_url: str = os.getenv("TRUST_REGISTRY_URL", "http://localhost:8000")
    jury_service_url: str = os.getenv("JURY_SERVICE_URL", "http://localhost:8001")
    ocx_gateway_url: str = os.getenv("OCX_GATEWAY_URL", "http://localhost:8002")
    activity_registry_url: str = os.getenv("ACTIVITY_REGISTRY_URL", "http://localhost:8003")
    evidence_vault_url: str = os.getenv("EVIDENCE_VAULT_URL", "http://localhost:8004")
    authority_url: str = os.getenv("AUTHORITY_URL", "http://localhost:8005")


@dataclass
class OCXConfig:
    """Master configuration container"""
    server: ServerConfig = field(default_factory=ServerConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    ai_models: AIModelsConfig = field(default_factory=AIModelsConfig)
    trust: TrustConfig = field(default_factory=TrustConfig)
    governance: GovernanceConfig = field(default_factory=GovernanceConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    spanner: SpannerConfig = field(default_factory=SpannerConfig)
    services: ServiceURLsConfig = field(default_factory=ServiceURLsConfig)


@lru_cache(maxsize=1)
def get_config() -> OCXConfig:
    """Get cached configuration instance"""
    return OCXConfig()


# Global config instance
config = get_config()


# Convenience functions
def is_production() -> bool:
    """Check if running in production"""
    return config.server.env == "production"


def is_development() -> bool:
    """Check if running in development"""
    return config.server.env == "development"


def get_database_url() -> str:
    """Get PostgreSQL connection URL"""
    db = config.database
    return f"postgresql://{db.postgres_user}:{db.postgres_password}@{db.postgres_host}:{db.postgres_port}/{db.postgres_db}"


def get_supabase_client():
    """Get Supabase client"""
    from supabase import create_client
    return create_client(config.database.supabase_url, config.database.supabase_service_key)
