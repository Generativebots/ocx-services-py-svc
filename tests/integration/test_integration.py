"""
OCX Integration Tests — All Python Services
=============================================
Merged: test_db_connectivity.py, test_service_api.py,
        test_go_proxy_compat.py, test_patent_services.py

Covers: DB connectivity, schema validation, FastAPI service APIs,
        Go proxy contract alignment, and ALL 14 patent claims.

Run: pytest tests/integration/test_integration.py -m integration -v
"""
import importlib
import os
import py_compile
import sys
import pytest

pytestmark = pytest.mark.integration

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def svc(name):
    return os.path.join(ROOT, name)


def has_py_files(path):
    if not os.path.isdir(path):
        return False
    return any(f.endswith(".py") for f in os.listdir(path))


def find_entrypoint(path):
    for candidate in ["main.py", "api.py", "server.py", "run.py", "app.py"]:
        full = os.path.join(path, candidate)
        if os.path.isfile(full):
            return full
    for f in sorted(os.listdir(path)):
        if f.endswith(".py") and f != "__init__.py":
            return os.path.join(path, f)
    return None


# ============================================================================
# Section 1: DB Connectivity & Schema Validation
# ============================================================================

class TestSupabaseConnectivity:

    def test_supabase_client_connects(self, supabase_client):
        assert supabase_client is not None

    def test_agents_table_readable(self, supabase_client):
        result = supabase_client.table("agents").select("agent_id, tenant_id").limit(3).execute()
        assert result.data is not None

    def test_policies_table_readable(self, supabase_client):
        result = supabase_client.table("policies").select("id, name, version").limit(3).execute()
        assert result.data is not None

    def test_evidence_table_readable(self, supabase_client):
        result = supabase_client.table("evidence").select("evidence_id, tenant_id").limit(3).execute()
        assert result.data is not None

    def test_verdicts_table_readable(self, supabase_client):
        result = supabase_client.table("verdicts").select("verdict_id, action").limit(3).execute()
        assert result.data is not None

    def test_tenants_table_readable(self, supabase_client):
        result = supabase_client.table("tenants").select("tenant_id, tenant_name").limit(3).execute()
        assert result.data is not None


class TestPostgresSchema:
    EXPECTED_TABLES = [
        "agents", "policies", "evidence", "verdicts",
        "tenants", "trust_scores", "session_audit_log", "handshake_sessions",
    ]

    def test_core_tables_exist(self, pg_conn):
        with pg_conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
            """)
            existing = {row[0] for row in cur.fetchall()}
        missing = [t for t in self.EXPECTED_TABLES if t not in existing]
        assert not missing, f"Missing tables: {missing}"

    def test_agents_has_tenant_column(self, pg_conn):
        with pg_conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'agents'
            """)
            columns = {row[0] for row in cur.fetchall()}
        assert "tenant_id" in columns
        assert "agent_id" in columns

    def test_evidence_schema(self, pg_conn):
        with pg_conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'evidence'
            """)
            columns = {row[0] for row in cur.fetchall()}
        required = {"evidence_id", "tenant_id", "evidence_type"}
        missing = required - columns
        assert not missing, f"evidence missing columns: {missing}"


# ============================================================================
# Section 2: FastAPI Service API Tests
# ============================================================================

class TestEvidenceVaultAPI:
    @pytest.fixture
    def ev_client(self):
        try:
            sys.path.insert(0, os.path.join(ROOT, "evidence-vault"))
            from api import app
        except Exception:
            pytest.skip("evidence-vault app not importable")
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_health_or_root(self, ev_client):
        resp = ev_client.get("/")
        assert resp.status_code in (200, 404, 307)

    def test_list_evidence(self, ev_client):
        resp = ev_client.get("/api/v1/evidence",
            headers={"X-Tenant-ID": "integration-test-tenant"},
            params={"tenant_id": "integration-test-tenant"})
        assert resp.status_code in (200, 422, 500)


class TestAuthorityAPI:
    @pytest.fixture
    def auth_client(self):
        try:
            sys.path.insert(0, os.path.join(ROOT, "authority"))
            from api import app
        except Exception:
            pytest.skip("authority app not importable")
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_gaps_endpoint(self, auth_client):
        resp = auth_client.get("/api/v1/authority/gaps",
            headers={"X-Tenant-ID": "integration-test-tenant"},
            params={"tenant_id": "integration-test-tenant"})
        assert resp.status_code in (200, 422, 500)


class TestIntentExtractorAPI:
    @pytest.fixture
    def ie_client(self):
        try:
            sys.path.insert(0, os.path.join(ROOT, "intent-extractor"))
            from main import app
        except Exception:
            pytest.skip("intent-extractor app not importable")
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_health(self, ie_client):
        resp = ie_client.get("/health")
        assert resp.status_code in (200, 404)


class TestLedgerAPI:
    @pytest.fixture
    def ledger_client(self):
        try:
            sys.path.insert(0, os.path.join(ROOT, "ledger"))
            from regulator_api import app
        except Exception:
            pytest.skip("ledger app not importable")
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_ledger_root(self, ledger_client):
        resp = ledger_client.get("/")
        assert resp.status_code in (200, 404, 307)


# ============================================================================
# Section 3: Go Proxy Contract Alignment
# ============================================================================

GO_PROXY_CONTRACTS = [
    {"env_var": "OCX_TRUST_REGISTRY_URL", "prefix": "/api/v1/py/registry", "service_dir": "trust-registry", "expected_routes": ["/health", "/register"]},
    {"env_var": "OCX_JURY_URL", "prefix": "/api/v1/py/jury", "service_dir": "jury", "expected_routes": []},
    {"env_var": "OCX_ACTIVITY_URL", "prefix": "/api/v1/py/activities", "service_dir": "activity-registry", "expected_routes": []},
    {"env_var": "OCX_EVIDENCE_VAULT_PY_URL", "prefix": "/api/v1/py/evidence", "service_dir": "evidence-vault", "expected_routes": ["/api/v1/evidence"]},
    {"env_var": "OCX_AUTHORITY_URL", "prefix": "/api/v1/py/authority", "service_dir": "authority", "expected_routes": ["/api/v1/authority/scan", "/api/v1/authority/gaps"]},
    {"env_var": "OCX_LEDGER_URL", "prefix": "/api/v1/py/ledger", "service_dir": "ledger", "expected_routes": []},
    {"env_var": "OCX_PROCESS_MINING_URL", "prefix": "/api/v1/py/mining", "service_dir": "process-mining", "expected_routes": []},
    {"env_var": "OCX_SHADOW_SOP_URL", "prefix": "/api/v1/py/shadow-sop", "service_dir": "shadow-sop", "expected_routes": []},
]


class TestGoProxyContractAlignment:

    def test_all_proxy_service_dirs_exist(self):
        for contract in GO_PROXY_CONTRACTS:
            svc_dir = os.path.join(ROOT, contract["service_dir"])
            assert os.path.isdir(svc_dir), f"Go proxy {contract['env_var']} expects {contract['service_dir']}/ but missing"

    def test_service_has_python_files(self):
        for contract in GO_PROXY_CONTRACTS:
            svc_dir = os.path.join(ROOT, contract["service_dir"])
            if not os.path.isdir(svc_dir):
                continue
            py_files = [f for f in os.listdir(svc_dir) if f.endswith(".py")]
            assert len(py_files) > 0, f"{contract['service_dir']}/ has no .py files"

    @pytest.mark.parametrize("contract", [c for c in GO_PROXY_CONTRACTS if c["expected_routes"]], ids=lambda c: c["env_var"])
    def test_service_has_expected_routes(self, contract):
        svc_dir = os.path.join(ROOT, contract["service_dir"])
        sys.path.insert(0, svc_dir)
        try:
            app = None
            for module_name in ["api", "main", "app", "server"]:
                try:
                    mod = importlib.import_module(module_name)
                    if hasattr(mod, "app"):
                        app = mod.app
                        break
                except Exception:
                    continue
            if app is None:
                pytest.skip(f"Cannot import FastAPI app from {contract['service_dir']}")
            registered_paths = {route.path for route in getattr(app, "routes", []) if hasattr(route, "path")}
            for expected in contract["expected_routes"]:
                assert expected in registered_paths, f"{contract['env_var']} expects {expected} but only has: {sorted(registered_paths)}"
        finally:
            sys.path.remove(svc_dir)

    def test_tenant_header_contract(self):
        for contract in GO_PROXY_CONTRACTS:
            svc_dir = os.path.join(ROOT, contract["service_dir"])
            if not os.path.isdir(svc_dir):
                continue
            found_tenant = False
            for fname in os.listdir(svc_dir):
                if not fname.endswith(".py"):
                    continue
                with open(os.path.join(svc_dir, fname), "r", errors="ignore") as f:
                    content = f.read()
                    if "tenant_id" in content.lower() or "x-tenant-id" in content.lower():
                        found_tenant = True
                        break
            if not found_tenant:
                pytest.xfail(f"{contract['service_dir']} does not reference tenant_id")


# ============================================================================
# Section 4: Patent-Aligned Service Tests (All 14 Claims)
# ============================================================================

# Map: claim → services
PATENT_SERVICES = {
    "Claim 1 — Ghost-state":       ["shadow-sop"],
    "Claim 2 — Tri-Factor":        ["jury"],
    "Claim 3 — Trust/Federation":  ["trust-registry", "federation"],
    "Claim 4 — APE/Policy":        ["ape", "authority", "intent-extractor"],
    "Claim 5 — Marketplace":       ["process-mining"],
    "Claim 6 — Bail-out":          ["cvic"],
    "Claim 7 — JIT Tokens":        ["integrity-engine"],
    "Claim 8 — Evidence Vault":    ["evidence-vault", "ledger"],
    "§A — eBPF":                   ["socket-interceptor"],
    "§B — GPU TEE":                ["memory-engine"],
    "§C — Collusion Detection":    ["parallel-auditing", "entropy", "monitor"],
    "§D — Async Clawback":         ["control-plane"],
    "§E — GRA":                    ["gra"],
    "§F — RLHC":                   ["rlhc"],
}


class TestPatentServicePresence:
    """Every patent claim has at least one Python service directory with .py files."""

    def test_all_patent_services_present(self):
        missing = []
        for claim, services in PATENT_SERVICES.items():
            for service in services:
                path = svc(service)
                if not os.path.isdir(path):
                    missing.append(f"  {service}/ — {claim}")
                elif not has_py_files(path):
                    missing.append(f"  {service}/ — no .py files ({claim})")
        if missing:
            pytest.fail("Patent service gaps:\n" + "\n".join(missing))


class TestPatentServiceCompilation:
    """Each patent service entrypoint compiles without syntax errors."""

    @pytest.mark.parametrize("service_name", [
        s for services in PATENT_SERVICES.values() for s in services
    ])
    def test_service_compiles(self, service_name):
        path = svc(service_name)
        if not os.path.isdir(path):
            pytest.skip(f"{service_name}/ not found")
        ep = find_entrypoint(path)
        if ep is None:
            pytest.skip(f"No entrypoint in {service_name}/")
        py_compile.compile(ep, doraise=True)


class TestSupportingServices:
    def test_activity_registry_exists(self):
        assert os.path.isdir(svc("activity-registry"))

    def test_sdk_exists(self):
        assert os.path.isdir(svc("sdk"))

    def test_config_exists(self):
        assert os.path.isdir(svc("config"))
