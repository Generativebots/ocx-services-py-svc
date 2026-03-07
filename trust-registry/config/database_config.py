"""
Database Backend Configuration

All services use Supabase (PostgreSQL) as the database backend.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """
    Database configuration manager.
    
    All tiers use Supabase/PostgreSQL as the database backend.
    
    Environment Variables:
    - SUPABASE_URL: Supabase project URL
    - SUPABASE_KEY / SUPABASE_SERVICE_KEY: Supabase API key
    - POSTGRES_HOST: Direct PostgreSQL host (fallback)
    - POSTGRES_PORT: PostgreSQL port
    - POSTGRES_DB: Database name
    - POSTGRES_USER: Database user
    - POSTGRES_PASSWORD: Database password
    """
    
    def __init__(self) -> None:
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load Supabase/PostgreSQL configuration"""
        return {
            "backend": "supabase",
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "ocx_trust"),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
            "supabase_url": os.getenv("SUPABASE_URL", ""),
            "supabase_key": os.getenv("SUPABASE_KEY", os.getenv("SUPABASE_SERVICE_KEY", "")),
            "ssl_mode": os.getenv("POSTGRES_SSL_MODE", "prefer"),
            "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        }
    
    def get_connection_string(self) -> str:
        """Get database connection string"""
        cfg = self.config
        return f"postgresql://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    
    def get_display_info(self) -> dict:
        """Get human-readable configuration info"""
        return {
            "backend": "supabase",
            "connection": self.get_connection_string(),
            "config": {k: v for k, v in self.config.items() if "password" not in k.lower() and "key" not in k.lower()}
        }


# Global configuration instance
db_config = DatabaseConfig()


def get_db_config() -> dict:
    """Get database configuration"""
    return db_config.config


def is_supabase_configured() -> bool:
    """Check if Supabase credentials are configured"""
    return bool(db_config.config.get("supabase_url") and db_config.config.get("supabase_key"))


def print_database_config() -> None:
    """Print current database configuration"""
    info = db_config.get_display_info()
    logger.info(f"Database Backend: {info['backend'].upper()}")
    logger.info(f"Connection: {info['connection']}")


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print_database_config()
