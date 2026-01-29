"""
Database Backend Configuration

Provides a switch between PostgreSQL/Supabase (default) and Cloud Spanner (enterprise).
Cloud Spanner is only enabled for clients at $10M+ tier.
"""

import os
from enum import Enum
from typing import Optional


class DatabaseBackend(Enum):
    """Database backend options"""
    POSTGRESQL = "postgresql"  # Default: Supabase/PostgreSQL
    SPANNER = "spanner"         # Enterprise: Cloud Spanner ($10M+ clients)


class ClientTier(Enum):
    """Client tier based on contract value"""
    STARTER = "starter"          # < $100K
    GROWTH = "growth"            # $100K - $1M
    ENTERPRISE = "enterprise"    # $1M - $10M
    GLOBAL = "global"            # $10M+


class DatabaseConfig:
    """
    Database configuration manager with automatic backend selection.
    
    Backend Selection Logic:
    - STARTER/GROWTH/ENTERPRISE: PostgreSQL/Supabase
    - GLOBAL ($10M+): Cloud Spanner
    
    Environment Variables:
    - DB_BACKEND: Force specific backend (postgresql|spanner)
    - CLIENT_TIER: Client tier (starter|growth|enterprise|global)
    - CLIENT_CONTRACT_VALUE: Contract value in USD
    """
    
    # Tier thresholds
    SPANNER_THRESHOLD = 10_000_000  # $10M
    
    def __init__(self):
        self.backend = self._determine_backend()
        self.config = self._load_config()
    
    def _determine_backend(self) -> DatabaseBackend:
        """Determine which database backend to use"""
        
        # 1. Check explicit override
        backend_override = os.getenv("DB_BACKEND", "").lower()
        if backend_override == "spanner":
            print("⚠️  Cloud Spanner explicitly enabled via DB_BACKEND")
            return DatabaseBackend.SPANNER
        elif backend_override == "postgresql":
            print("✅ PostgreSQL explicitly enabled via DB_BACKEND")
            return DatabaseBackend.POSTGRESQL
        
        # 2. Check client tier
        client_tier = os.getenv("CLIENT_TIER", "starter").lower()
        if client_tier == "global":
            print("✅ Cloud Spanner enabled: Client tier = GLOBAL ($10M+)")
            return DatabaseBackend.SPANNER
        
        # 3. Check contract value
        try:
            contract_value = float(os.getenv("CLIENT_CONTRACT_VALUE", "0"))
            if contract_value >= self.SPANNER_THRESHOLD:
                print(f"✅ Cloud Spanner enabled: Contract value = ${contract_value:,.0f}")
                return DatabaseBackend.SPANNER
        except ValueError:
            pass
        
        # 4. Default to PostgreSQL
        print("✅ PostgreSQL/Supabase enabled (default)")
        return DatabaseBackend.POSTGRESQL
    
    def _load_config(self) -> dict:
        """Load configuration for selected backend"""
        
        if self.backend == DatabaseBackend.SPANNER:
            return self._load_spanner_config()
        else:
            return self._load_postgresql_config()
    
    def _load_postgresql_config(self) -> dict:
        """Load PostgreSQL/Supabase configuration"""
        return {
            "backend": "postgresql",
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "ocx_trust"),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
            "supabase_url": os.getenv("SUPABASE_URL", ""),
            "supabase_key": os.getenv("SUPABASE_KEY", ""),
            "ssl_mode": os.getenv("POSTGRES_SSL_MODE", "prefer"),
            "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        }
    
    def _load_spanner_config(self) -> dict:
        """Load Cloud Spanner configuration"""
        return {
            "backend": "spanner",
            "project_id": os.getenv("GCP_PROJECT_ID", ""),
            "instance_id": os.getenv("SPANNER_INSTANCE_ID", "ocx-global"),
            "database_id": os.getenv("SPANNER_DATABASE_ID", "trust-ledger"),
            "credentials_path": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
            "pool_size": int(os.getenv("SPANNER_POOL_SIZE", "10")),
            "timeout": int(os.getenv("SPANNER_TIMEOUT", "30")),
        }
    
    def is_spanner_enabled(self) -> bool:
        """Check if Cloud Spanner is enabled"""
        return self.backend == DatabaseBackend.SPANNER
    
    def is_postgresql_enabled(self) -> bool:
        """Check if PostgreSQL is enabled"""
        return self.backend == DatabaseBackend.POSTGRESQL
    
    def get_connection_string(self) -> str:
        """Get database connection string"""
        if self.backend == DatabaseBackend.POSTGRESQL:
            cfg = self.config
            return f"postgresql://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
        else:
            cfg = self.config
            return f"spanner://{cfg['project_id']}/{cfg['instance_id']}/{cfg['database_id']}"
    
    def get_display_info(self) -> dict:
        """Get human-readable configuration info"""
        return {
            "backend": self.backend.value,
            "enabled_for": self._get_tier_description(),
            "connection": self.get_connection_string(),
            "config": {k: v for k, v in self.config.items() if "password" not in k.lower() and "key" not in k.lower()}
        }
    
    def _get_tier_description(self) -> str:
        """Get description of when this backend is enabled"""
        if self.backend == DatabaseBackend.SPANNER:
            return "GLOBAL tier clients ($10M+ contract value)"
        else:
            return "STARTER, GROWTH, ENTERPRISE tiers (< $10M)"


# Global configuration instance
db_config = DatabaseConfig()


def get_database_backend() -> DatabaseBackend:
    """Get the current database backend"""
    return db_config.backend


def is_spanner_enabled() -> bool:
    """Check if Cloud Spanner is enabled"""
    return db_config.is_spanner_enabled()


def is_postgresql_enabled() -> bool:
    """Check if PostgreSQL is enabled"""
    return db_config.is_postgresql_enabled()


def get_db_config() -> dict:
    """Get database configuration"""
    return db_config.config


def print_database_config():
    """Print current database configuration"""
    info = db_config.get_display_info()
    print("\n" + "="*60)
    print("DATABASE CONFIGURATION")
    print("="*60)
    print(f"Backend:      {info['backend'].upper()}")
    print(f"Enabled For:  {info['enabled_for']}")
    print(f"Connection:   {info['connection']}")
    print("\nConfiguration:")
    for key, value in info['config'].items():
        print(f"  {key}: {value}")
    print("="*60 + "\n")


# Example usage and testing
if __name__ == "__main__":
    print_database_config()
    
    # Test different scenarios
    print("\n📊 Testing Different Client Tiers:\n")
    
    scenarios = [
        ("STARTER", "50000", "PostgreSQL"),
        ("GROWTH", "500000", "PostgreSQL"),
        ("ENTERPRISE", "5000000", "PostgreSQL"),
        ("GLOBAL", "15000000", "Cloud Spanner"),
    ]
    
    for tier, value, expected in scenarios:
        os.environ["CLIENT_TIER"] = tier.lower()
        os.environ["CLIENT_CONTRACT_VALUE"] = value
        
        test_config = DatabaseConfig()
        backend = "Cloud Spanner" if test_config.is_spanner_enabled() else "PostgreSQL"
        status = "✅" if backend == expected else "❌"
        
        print(f"{status} {tier:12} (${int(value):>10,}) → {backend}")
    
    # Reset to default
    os.environ.pop("CLIENT_TIER", None)
    os.environ.pop("CLIENT_CONTRACT_VALUE", None)
