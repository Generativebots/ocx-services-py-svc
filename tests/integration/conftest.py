"""
Cross-Stack Integration Test Fixtures
=====================================
Shared fixtures for integration tests that require:
- Real Supabase/PostgreSQL connectivity
- Test tenant context
- Auto-cleanup of test data
"""
import os
import sys
import pytest

# Ensure all service packages are importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_env():
    """Load .env file if dotenv is available."""
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(ROOT, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)
    except ImportError:
        pass


_load_env()


@pytest.fixture(scope="session")
def supabase_url():
    """Supabase project URL from environment."""
    url = os.getenv("SUPABASE_URL")
    if not url:
        pytest.skip("SUPABASE_URL not set — skipping integration tests")
    return url


@pytest.fixture(scope="session")
def supabase_key():
    """Supabase service role key from environment."""
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not key:
        pytest.skip("SUPABASE_SERVICE_KEY not set — skipping integration tests")
    return key


@pytest.fixture(scope="session")
def supabase_client(supabase_url, supabase_key):
    """Real Supabase client for integration tests."""
    try:
        from supabase import create_client
        client = create_client(supabase_url, supabase_key)
        return client
    except ImportError:
        pytest.skip("supabase-py not installed")
    except Exception as e:
        pytest.skip(f"Cannot create Supabase client: {e}")


@pytest.fixture(scope="session")
def pg_conn():
    """Direct PostgreSQL connection for schema verification."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "db.ohdttatdawcvopzthwwi.supabase.co"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("POSTGRES_DB", "postgres"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            connect_timeout=10,
        )
        yield conn
        conn.close()
    except ImportError:
        pytest.skip("psycopg2 not installed")
    except Exception as e:
        pytest.skip(f"Cannot connect to PostgreSQL: {e}")


@pytest.fixture
def integration_tenant_id():
    """Dedicated tenant ID for integration tests — avoids polluting real data."""
    return "integration-test-tenant"


@pytest.fixture
def cleanup_agent_ids():
    """Collector for agent IDs to clean up after test."""
    ids = []
    yield ids
    # Cleanup happens in individual tests using supabase_client
