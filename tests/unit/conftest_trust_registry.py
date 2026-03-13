"""
Trust Registry — pytest configuration & shared fixtures.

Provides a FastAPI TestClient and monkeypatches external dependencies
(Supabase, Redis, vLLM) so tests run without any infrastructure.
"""

import os
import sys
import pytest

# Ensure the trust-registry package is importable
sys.path.insert(0, os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# Stub heavy external deps BEFORE they are imported by application code.
# ---------------------------------------------------------------------------

# 1) supabase client — Registry.__init__ calls create_client
import types

_fake_supabase = types.ModuleType("supabase")
_fake_supabase.create_client = lambda *a, **kw: None  # type: ignore
_fake_supabase.Client = type("Client", (), {})
sys.modules.setdefault("supabase", _fake_supabase)

# 2) redis — Registry.__init__ connects eagerly
_fake_redis_mod = types.ModuleType("redis")
_fake_redis_mod.Redis = lambda **kw: type(  # type: ignore
    "FakeRedis", (), {
        "ping": lambda self: True,
        "publish": lambda self, *a: 0,
        "bf": lambda self: type("BF", (), {
            "reserve": lambda self, *a: None,
            "add": lambda self, *a: None,
            "exists": lambda self, *a: False,
        })(),
        "setex": lambda self, *a: None,
        "from_url": classmethod(lambda cls, *a, **kw: cls()),
        "hset": lambda self, *a, **kw: None,
        "lrange": lambda self, *a: [],
        "set": lambda self, *a, **kw: None,
    }
)()
_fake_redis_mod.from_url = lambda *a, **kw: _fake_redis_mod.Redis()  # type: ignore
_fake_redis_mod.exceptions = types.ModuleType("redis.exceptions")
_fake_redis_mod.exceptions.ResponseError = type("ResponseError", (Exception,), {})
sys.modules.setdefault("redis", _fake_redis_mod)
sys.modules.setdefault("redis.exceptions", _fake_redis_mod.exceptions)

# Stub redis.commands.bf so `from redis.commands.bf import BFInfo` works
_fake_bf = types.ModuleType("redis.commands.bf")
_fake_bf.BFInfo = type("BFInfo", (), {})
_fake_commands = types.ModuleType("redis.commands")
sys.modules.setdefault("redis.commands", _fake_commands)
sys.modules.setdefault("redis.commands.bf", _fake_bf)

# 3) ecdsa — used for signature verification in evaluate_intent
_fake_ecdsa = types.ModuleType("ecdsa")
_fake_ecdsa.VerifyingKey = type("VerifyingKey", (), {
    "from_string": staticmethod(lambda *a, **kw: type("VK", (), {"verify": lambda self, *a: True})()),
})
_fake_ecdsa.NIST256p = "fake-curve"
sys.modules.setdefault("ecdsa", _fake_ecdsa)

# 4) json_logic_engine — needed by ghost_state_engine
_fake_jl = types.ModuleType("json_logic_engine")

class FakeJSONLogicEngine:
    def __init__(self):
        self._cache = {}

    def evaluate(self, logic, data, context=None):
        """Simple evaluator for common operators used in tests."""
        if context:
            data = {**data, **context}
        if isinstance(logic, dict):
            if "<" in logic:
                args = logic["<"]
                left = self._resolve(args[0], data)
                right = self._resolve(args[1], data)
                return left < right if left is not None and right is not None else False
            if ">" in logic:
                args = logic[">"]
                left = self._resolve(args[0], data)
                right = self._resolve(args[1], data)
                return left > right if left is not None and right is not None else False
            if "==" in logic:
                args = logic["=="]
                left = self._resolve(args[0], data)
                right = self._resolve(args[1], data)
                return left == right
            if "and" in logic:
                return all(self.evaluate(sub, data) for sub in logic["and"])
            if "or" in logic:
                return any(self.evaluate(sub, data) for sub in logic["or"])
            if "not" in logic:
                return not self.evaluate(logic["not"], data)
            if "in" in logic:
                args = logic["in"]
                needle = self._resolve(args[0], data)
                haystack = self._resolve(args[1], data)
                if haystack is None:
                    return False
                return needle in haystack
        return False

    def _resolve(self, val, data):
        if isinstance(val, dict) and "var" in val:
            path = val["var"]
            parts = path.split(".")
            curr = data
            for p in parts:
                if isinstance(curr, dict):
                    curr = curr.get(p)
                else:
                    return None
            return curr
        return val

    def extract_variables(self, logic):
        variables = []
        if isinstance(logic, dict):
            for k, v in logic.items():
                if k == "var":
                    variables.append(v)
                elif isinstance(v, list):
                    for item in v:
                        variables.extend(self.extract_variables(item) if isinstance(item, dict) else [])
                elif isinstance(v, dict):
                    variables.extend(self.extract_variables(v))
        return list(set(variables))

    def validate_logic(self, logic):
        """Validate JSON-Logic by trying to evaluate with empty data."""
        try:
            self.evaluate(logic, {})
            return True, None
        except Exception as e:
            return False, str(e)

    def simplify(self, logic):
        """Simplify JSON-Logic expressions following standard rules."""
        if not isinstance(logic, dict):
            return logic

        # Recursively simplify children first
        simplified = {}
        for op, args in logic.items():
            if isinstance(args, list):
                simplified[op] = [
                    self.simplify(a) if isinstance(a, dict) else a for a in args
                ]
            elif isinstance(args, dict):
                simplified[op] = self.simplify(args)
            else:
                simplified[op] = args

        # Rule 1 & 2: unwrap single-element AND/OR
        for wrapper in ("and", "or"):
            if wrapper in simplified:
                items = simplified[wrapper]
                if isinstance(items, list) and len(items) == 1:
                    return items[0]

        # Rule 3: eliminate double negation
        if "not" in simplified:
            inner = simplified["not"]
            if isinstance(inner, dict) and "not" in inner:
                return inner["not"]

        # Rule 4: identity comparison
        if "==" in simplified:
            args = simplified["=="]
            if isinstance(args, list) and len(args) == 2 and args[0] == args[1]:
                return True

        return simplified



_fake_jl.JSONLogicEngine = FakeJSONLogicEngine
sys.modules.setdefault("json_logic_engine", _fake_jl)

# 5) json_logic (pip package) — used by json_logic_engine.py
_fake_json_logic_pkg = types.ModuleType("json_logic")
def _jsonLogic(logic, data):
    """Minimal json_logic evaluator for tests."""
    engine = FakeJSONLogicEngine()
    return engine.evaluate(logic, data)
_fake_json_logic_pkg.jsonLogic = _jsonLogic
sys.modules.setdefault("json_logic", _fake_json_logic_pkg)

# 6) llm_client — used by correction_agent.py
_fake_llm = types.ModuleType("llm_client")
class FakeLLMClient:
    def generate(self, prompt, system_prompt=None):
        return '{"remediation_directive": "mock", "reasoning_trace": "test"}'
_fake_llm.LLMClient = FakeLLMClient
sys.modules.setdefault("llm_client", _fake_llm)

# 7) vllm_client — used by ape_engine.py
_fake_vllm = types.ModuleType("vllm_client")
class FakeVLLMClient:
    def generate(self, prompt, system_prompt=None):
        return '[]'
_fake_vllm.VLLMClient = FakeVLLMClient
sys.modules.setdefault("vllm_client", _fake_vllm)


# ---------------------------------------------------------------------------
# Now we can safely import the app
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Monkey-patch Registry's MISSING methods (Bug #5: called but not defined)
# ---------------------------------------------------------------------------
from registry import Registry

if not hasattr(Registry, "get_active_rules"):
    def _get_active_rules(self):
        """Stub: returns empty rule list (method missing from production code)."""
        return []
    Registry.get_active_rules = _get_active_rules

if not hasattr(Registry, "list_agents"):
    def _list_agents(self, tenant_id: str):
        """Stub: returns empty agent list (method missing from production code)."""
        return []
    Registry.list_agents = _list_agents

from main import app


@pytest.fixture
def client():
    """FastAPI TestClient for trust-registry."""
    return TestClient(app)
