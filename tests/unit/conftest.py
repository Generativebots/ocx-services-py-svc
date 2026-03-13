"""
OCX Python Services — Unit Test conftest.py
============================================
Adds service directories to sys.path so bare-module imports resolve correctly.

Name-collision strategy
-----------------------
Several directories share generic names (``main.py`` in 4 services, ``api.py``
in 4 services, ``jury/`` package vs ``trust-registry/jury.py``, etc.).

We handle this by:
1. Adding ONLY non-conflicting dirs to sys.path (no ``shadow-sop/``).
2. Using ``importlib.util`` to register specific modules under the bare names
   that tests expect, overriding empty ``__init__.py`` packages at the root.
3. NOT adding dirs with ``main.py`` to the global sys.path — each test file
   that needs a specific ``main.py`` must set its own path before importing.

Dirs with ``main.py`` (NOT added globally): monitor/, trust-registry/,
intent-extractor/, process-mining/.

Tests for these services add the correct dir to sys.path themselves.
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ──────────────────────────────────────────────────────────────────────────────
# 1.  Safe service directories — no ``main.py``, ``api.py``, or package-name
#     collisions with root-level dirs.
# ──────────────────────────────────────────────────────────────────────────────

SERVICE_DIRS = [
    "activity-registry",
    "ape",
    "authority",
    "authority/config",
    "config",
    "control-plane",
    "cvic",
    "entropy",
    "federation",
    "gra",
    "integrity-engine",
    "ledger",
    "memory-engine",
    "parallel-auditing",
    "sdk",
    "socket-interceptor",
    # ──────────────────────────────────────────────────────────────────────
    # EXCLUDED dirs (collision risk):
    # shadow-sop     — has api.py, rlhc.py that collide with packages
    # evidence-vault — has api.py that collides with activity-registry/api.py
    # monitor        — has main.py; its __init__.py also shadows entropy/monitor.py
    # trust-registry — has main.py, jury.py (collides with jury/ package)
    # intent-extractor — has main.py
    # process-mining — has main.py
    # jury           — package dir, but tests need trust-registry/jury.py
    # rlhc           — package dir
    # ──────────────────────────────────────────────────────────────────────
]

for d in SERVICE_DIRS:
    path = os.path.join(ROOT, d)
    if path not in sys.path and os.path.isdir(path):
        sys.path.insert(0, path)

# ──────────────────────────────────────────────────────────────────────────────
# 2.  importlib overrides: register the correct *file* module under the
#     bare name the tests expect, overriding empty packages at the root.
# ──────────────────────────────────────────────────────────────────────────────

def _register_module(mod_name: str, file_path: str) -> None:
    """Register a .py file as a module in sys.modules under ``mod_name``."""
    if not os.path.isfile(file_path):
        return
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            # Module stays in sys.modules so the test gets a clear traceback
            pass


# entropy/monitor.py  ⟶  ``from monitor import calculate_shannon_entropy``
# (overrides the empty ``monitor/__init__.py`` package)
_register_module("monitor", os.path.join(ROOT, "entropy", "monitor.py"))
