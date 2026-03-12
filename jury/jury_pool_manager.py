"""
AOCS Jury Pool Manager — Dynamic Pool Sizing, Rotation & VRF Selection

Implements CIP Patent claims for multi-model jury pool management:
  - Configurable model registry (from tenant governance config)
  - Dynamic pool sizing based on risk levels (3→N jurors)
  - Pool rotation for anti-collusion
  - Optional VRF-based deterministic juror selection

All API keys are resolved from the tenant governance config (Supabase),
with environment variable fallback for platform-level defaults only.
"""

import hashlib
import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class JurorModelEntry:
    """A registered juror model in the pool registry."""
    provider: str         # 'openai', 'anthropic', 'gemini'
    model_name: str       # 'gpt-4o-mini', 'claude-3-5-haiku-latest', etc.
    juror_role: str        # 'Compliance Expert', 'Security Analyst', etc.
    juror_id: str          # unique juror identifier
    weight: float = 1.0
    enabled: bool = True
    api_key_field: str = ""  # field name in governance config, e.g. 'openai_api_key'
    api_key_env: str = ""    # fallback env var, e.g. 'OPENAI_API_KEY'
    endpoint: str = ""       # provider API endpoint


@dataclass
class JuryPoolConfig:
    """Pool sizing, rotation, and VRF configuration."""
    min_jurors: int = 3
    max_jurors: int = 7
    risk_thresholds: Dict[str, int] = field(default_factory=lambda: {
        "LOW": 3,
        "MEDIUM": 5,
        "HIGH": 7,
        "CRITICAL": 7,
    })
    rotation_enabled: bool = True
    rotation_interval_hours: int = 24
    vrf_enabled: bool = False
    vrf_seed: str = ""


# ============================================================================
# DEFAULT MODEL REGISTRY
# ============================================================================

DEFAULT_MODELS: List[JurorModelEntry] = [
    JurorModelEntry(
        provider="openai",
        model_name="gpt-4o-mini",
        juror_role="Compliance Expert — focus on regulatory and policy adherence",
        juror_id="juror-compliance",
        weight=1.0,
        api_key_field="openai_api_key",
        api_key_env="OPENAI_API_KEY",
        endpoint="https://api.openai.com/v1/chat/completions",
    ),
    JurorModelEntry(
        provider="anthropic",
        model_name="claude-3-5-haiku-latest",
        juror_role="Security Analyst — focus on attack vectors, data exfiltration, privilege escalation",
        juror_id="juror-security",
        weight=1.0,
        api_key_field="anthropic_api_key",
        api_key_env="ANTHROPIC_API_KEY",
        endpoint="https://api.anthropic.com/v1/messages",
    ),
    JurorModelEntry(
        provider="gemini",
        model_name="gemini-2.0-flash",
        juror_role="Business Logic Validator — focus on business impact, cost, and operational risk",
        juror_id="juror-business",
        weight=1.0,
        api_key_field="gemini_api_key",
        api_key_env="GEMINI_API_KEY",
        endpoint="",  # Gemini uses dynamic URL with API key
    ),
]


# ============================================================================
# JURY POOL MANAGER
# ============================================================================

class JuryPoolManager:
    """
    Manages the jury pool: model registry, dynamic sizing, rotation, and VRF.

    Usage:
        manager = JuryPoolManager(tenant_id="acme-corp")
        jurors = manager.select_jurors(risk_level="HIGH")
        # jurors is a list of LLMJurorClient instances
    """

    def __init__(self, tenant_id: str = ""):
        self.tenant_id = tenant_id
        self._tenant_cfg = self._load_tenant_config(tenant_id)
        self.model_registry = self._load_model_registry()
        self.pool_config = self._load_pool_config()
        self._rotation_epoch_override: Optional[int] = None

        enabled_count = sum(1 for m in self.model_registry if m.enabled)
        logger.info(
            f"JuryPoolManager initialized: {enabled_count}/{len(self.model_registry)} "
            f"models enabled, tenant={tenant_id or 'platform'}, "
            f"vrf={self.pool_config.vrf_enabled}, "
            f"rotation_interval={self.pool_config.rotation_interval_hours}h"
        )

    # ── Config Loading ────────────────────────────────────────────────────

    @staticmethod
    def _load_tenant_config(tenant_id: str) -> Dict[str, Any]:
        """Load tenant governance config from Supabase."""
        if not tenant_id:
            return {}
        try:
            from config.governance_config import get_tenant_governance_config
            return get_tenant_governance_config(tenant_id)
        except Exception as e:
            logger.warning(f"Failed to load tenant config for {tenant_id}: {e}")
            return {}

    def _load_model_registry(self) -> List[JurorModelEntry]:
        """
        Load juror model registry from tenant governance config.

        Expected config shape:
            {
                "jury_pool_models": [
                    {"provider": "openai", "model_name": "gpt-4o-mini", ...},
                    ...
                ]
            }

        Falls back to DEFAULT_MODELS if not configured.
        """
        models_cfg = self._tenant_cfg.get("jury_pool_models", None)
        if not models_cfg or not isinstance(models_cfg, list):
            return [JurorModelEntry(**{
                k: v for k, v in m.__dict__.items()
            }) for m in DEFAULT_MODELS]

        registry = []
        for entry in models_cfg:
            try:
                registry.append(JurorModelEntry(
                    provider=entry.get("provider", "unknown"),
                    model_name=entry.get("model_name", "unknown"),
                    juror_role=entry.get("juror_role", "General Reviewer"),
                    juror_id=entry.get("juror_id", f"juror-{entry.get('provider', 'x')}"),
                    weight=float(entry.get("weight", 1.0)),
                    enabled=bool(entry.get("enabled", True)),
                    api_key_field=entry.get("api_key_field", ""),
                    api_key_env=entry.get("api_key_env", ""),
                    endpoint=entry.get("endpoint", ""),
                ))
            except Exception as e:
                logger.warning(f"Skipping invalid model registry entry: {e}")
        return registry if registry else [JurorModelEntry(**{
            k: v for k, v in m.__dict__.items()
        }) for m in DEFAULT_MODELS]

    def _load_pool_config(self) -> JuryPoolConfig:
        """
        Load pool configuration from tenant governance config.

        Expected config shape:
            {
                "jury_pool_config": {
                    "min_jurors": 3, "max_jurors": 7,
                    "risk_thresholds": {"LOW": 3, "MEDIUM": 5, ...},
                    "rotation_enabled": true,
                    "rotation_interval_hours": 24,
                    "vrf_enabled": false, "vrf_seed": ""
                }
            }
        """
        cfg = self._tenant_cfg.get("jury_pool_config", None)
        if not cfg or not isinstance(cfg, dict):
            return JuryPoolConfig()

        risk_thresholds = cfg.get("risk_thresholds", None)
        if risk_thresholds and isinstance(risk_thresholds, dict):
            # Ensure all keys are present
            defaults = {"LOW": 3, "MEDIUM": 5, "HIGH": 7, "CRITICAL": 7}
            defaults.update({k: int(v) for k, v in risk_thresholds.items()})
            risk_thresholds = defaults
        else:
            risk_thresholds = {"LOW": 3, "MEDIUM": 5, "HIGH": 7, "CRITICAL": 7}

        return JuryPoolConfig(
            min_jurors=int(cfg.get("min_jurors", 3)),
            max_jurors=int(cfg.get("max_jurors", 7)),
            risk_thresholds=risk_thresholds,
            rotation_enabled=bool(cfg.get("rotation_enabled", True)),
            rotation_interval_hours=int(cfg.get("rotation_interval_hours", 24)),
            vrf_enabled=bool(cfg.get("vrf_enabled", False)),
            vrf_seed=str(cfg.get("vrf_seed", "")),
        )

    # ── Juror Selection ───────────────────────────────────────────────────

    def _resolve_api_key(self, model: JurorModelEntry) -> str:
        """Resolve API key: tenant config → env var → empty."""
        if model.api_key_field:
            key = self._tenant_cfg.get(model.api_key_field, "")
            if key:
                return key
        if model.api_key_env:
            return os.environ.get(model.api_key_env, "")
        return ""

    def _get_rotation_epoch(self) -> int:
        """Current rotation epoch based on UTC hours."""
        if self._rotation_epoch_override is not None:
            return self._rotation_epoch_override
        interval = max(1, self.pool_config.rotation_interval_hours)
        return int(time.time() // (interval * 3600))

    def _vrf_shuffle(self, models: List[JurorModelEntry], epoch: int) -> List[JurorModelEntry]:
        """
        VRF-based deterministic shuffle using SHA-256.

        Produces a repeatable ordering for the same seed + epoch,
        ensuring verifiable randomness for high-security tenants.
        """
        seed = self.pool_config.vrf_seed or self.tenant_id or "default"
        hash_input = f"{seed}:{epoch}".encode("utf-8")
        digest = hashlib.sha256(hash_input).hexdigest()

        # Generate a sort key for each model using hash slices
        keyed = []
        for i, model in enumerate(models):
            # Use different slices of the hash for each model
            slice_start = (i * 8) % (len(digest) - 8)
            sort_key = int(digest[slice_start:slice_start + 8], 16)
            keyed.append((sort_key, model))

        keyed.sort(key=lambda x: x[0])
        return [m for _, m in keyed]

    def _round_robin_select(
        self, models: List[JurorModelEntry], count: int, epoch: int
    ) -> List[JurorModelEntry]:
        """Round-robin selection with epoch-based offset for rotation."""
        if not models:
            return []
        offset = epoch % len(models) if self.pool_config.rotation_enabled else 0
        selected = []
        for i in range(count):
            idx = (offset + i) % len(models)
            selected.append(models[idx])
        return selected

    def select_jurors(self, risk_level: str = "MEDIUM") -> List:
        """
        Select N jurors from the registry based on risk level.

        Returns a list of LLMJurorClient instances ready for evaluation.
        """
        # 1. Determine pool size from risk thresholds
        target_count = self.pool_config.risk_thresholds.get(
            risk_level.upper(),
            self.pool_config.risk_thresholds.get("MEDIUM", 5),
        )
        target_count = max(self.pool_config.min_jurors,
                          min(target_count, self.pool_config.max_jurors))

        # 2. Filter to enabled models
        enabled_models = [m for m in self.model_registry if m.enabled]
        if not enabled_models:
            logger.warning("No enabled models in registry, using defaults")
            enabled_models = list(DEFAULT_MODELS)

        # 3. Cap target to available models
        target_count = min(target_count, len(enabled_models))

        # 4. Select models via VRF or round-robin
        epoch = self._get_rotation_epoch()
        if self.pool_config.vrf_enabled:
            shuffled = self._vrf_shuffle(enabled_models, epoch)
            selected_models = shuffled[:target_count]
        else:
            selected_models = self._round_robin_select(
                enabled_models, target_count, epoch
            )

        # 5. Instantiate LLMJurorClient objects
        jurors = []
        for model in selected_models:
            api_key = self._resolve_api_key(model)
            juror = self._create_juror_client(model, api_key)
            jurors.append(juror)

        logger.info(
            f"Selected {len(jurors)} jurors for risk_level={risk_level}: "
            f"{[j.juror_id for j in jurors]} (epoch={epoch}, vrf={self.pool_config.vrf_enabled})"
        )
        return jurors

    def _create_juror_client(self, model: JurorModelEntry, api_key: str):
        """Create the appropriate LLMJurorClient subclass for the model."""
        from llm_juror import OpenAIJuror, AnthropicJuror, GeminiJuror, LLMJurorClient

        provider = model.provider.lower()

        if provider == "openai":
            juror = OpenAIJuror(api_key=api_key, weight_boost=model.weight)
            juror.juror_id = model.juror_id
            juror.role = model.juror_role
            juror.model_name = model.model_name
            return juror
        elif provider == "anthropic":
            juror = AnthropicJuror(api_key=api_key, weight_boost=model.weight)
            juror.juror_id = model.juror_id
            juror.role = model.juror_role
            juror.model_name = model.model_name
            return juror
        elif provider == "gemini":
            juror = GeminiJuror(api_key=api_key, weight_boost=model.weight)
            juror.juror_id = model.juror_id
            juror.role = model.juror_role
            juror.model_name = model.model_name
            return juror
        else:
            # Generic client for unknown providers
            return LLMJurorClient(
                juror_id=model.juror_id,
                role=model.juror_role,
                model_name=model.model_name,
                api_key=api_key,
                api_key_env=model.api_key_env,
                endpoint=model.endpoint,
                weight_boost=model.weight,
            )

    # ── Pool Status & Rotation ────────────────────────────────────────────

    def get_pool_status(self) -> Dict[str, Any]:
        """Return current pool state for API/UI display."""
        epoch = self._get_rotation_epoch()
        interval = max(1, self.pool_config.rotation_interval_hours)
        next_rotation_ts = (epoch + 1) * interval * 3600

        return {
            "tenant_id": self.tenant_id or "platform",
            "registered_models": len(self.model_registry),
            "enabled_models": sum(1 for m in self.model_registry if m.enabled),
            "models": [
                {
                    "provider": m.provider,
                    "model_name": m.model_name,
                    "juror_id": m.juror_id,
                    "juror_role": m.juror_role,
                    "weight": m.weight,
                    "enabled": m.enabled,
                    "has_api_key": bool(self._resolve_api_key(m)),
                }
                for m in self.model_registry
            ],
            "pool_config": {
                "min_jurors": self.pool_config.min_jurors,
                "max_jurors": self.pool_config.max_jurors,
                "risk_thresholds": self.pool_config.risk_thresholds,
                "rotation_enabled": self.pool_config.rotation_enabled,
                "rotation_interval_hours": self.pool_config.rotation_interval_hours,
                "vrf_enabled": self.pool_config.vrf_enabled,
            },
            "rotation_epoch": epoch,
            "next_rotation_unix": next_rotation_ts,
            "vrf_active": self.pool_config.vrf_enabled and bool(
                self.pool_config.vrf_seed or self.tenant_id
            ),
        }

    def rotate_pool(self) -> Dict[str, Any]:
        """Force a pool rotation by advancing the epoch."""
        old_epoch = self._get_rotation_epoch()
        self._rotation_epoch_override = old_epoch + 1
        new_epoch = self._get_rotation_epoch()
        logger.info(f"Forced pool rotation: epoch {old_epoch} → {new_epoch}")
        return {
            "previous_epoch": old_epoch,
            "new_epoch": new_epoch,
            "status": "rotated",
        }
