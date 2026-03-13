"""
Monitor — pytest configuration & shared fixtures.

Stubs Redis to avoid needing a running Redis instance.
"""

import os
import sys
import types
import pytest

sys.path.insert(0, os.path.dirname(__file__))

# Stub redis before importing the app
_fake_redis = types.ModuleType("redis")


class FakeRedisConn:
    def ping(self):
        return True
    def lrange(self, *a):
        return []
    def hset(self, *a, **kw):
        return None
    def set(self, *a, **kw):
        return None


def _from_url(*a, **kw):
    return FakeRedisConn()


_fake_redis.from_url = _from_url
_fake_redis.Redis = lambda **kw: FakeRedisConn()
sys.modules.setdefault("redis", _fake_redis)

from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    """FastAPI TestClient for monitor."""
    return TestClient(app)
