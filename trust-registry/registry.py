import os
import json
import uuid
import datetime
import threading
import logging
from typing import Any, List, Optional
from supabase import create_client, Client
import redis
from redis.commands.bf import BFInfo

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Registry:
    """
    Manages mutable configuration: Registered Agents and Business Rules.
    Backend: Supabase (Postgres) + Redis (Cache/PubSub).
    Multi-Tenancy: Enforced via `tenant_id` and RLS.
    """
    def __init__(self) -> None:
        # 1. Supabase Init
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        if not self.supabase_url or not self.supabase_key:
            logger.warning("Supabase credentials not found. Registry running in limited mode.")
            self.supabase: Optional[Client] = None
        else:
            self.supabase = create_client(self.supabase_url, self.supabase_key)

        # 2. Redis Init (Hot Storage & Bloom Filters)
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis = redis.Redis(host=self.redis_host, port=self.redis_port, decode_responses=True)
        
        # 3. Hydrate Bloom Filters & Start Realtime
        if self.supabase:
            self.hydrate_cache()
            # self.start_realtime_listener() # Requires asyncio loop handling

    def hydrate_cache(self) -> None:
        """
        Hydrates Redis Bloom Filters from Supabase on startup.
        """
        logger.info("Hydrating Bloom Filters from Supabase...")
        try:
            # Fetch all active rules (RLS will filter by service_role if used, 
            # here we act as system admin for cache hydration)
            response = self.supabase.table("rules").select("rule_id, tenant_id").eq("status", "Active").execute()
            
            # Setup Bloom Filter
            bf_key = "rules:bf"
            try:
                self.redis.bf().reserve(bf_key, 0.01, 10000)
            except redis.exceptions.ResponseError:
                pass # Already exists

            count = 0
            for row in response.data:
                # Key: tenant_id:rule_id (Composite key for bloom)
                item = f"{row['tenant_id']}:{row['rule_id']}"
                self.redis.bf().add(bf_key, item)
                count += 1
            
            logger.info(f"Hydrated {count} rules into Redis Bloom Filter.")
        except Exception as e:
            logger.error(f"Failed to hydrate cache: {e}")

    def register_agent(self, agent_json: dict, tenant_id: str) -> Any:
        """
        Registers an agent using the full OCX JSON Schema into Supabase.
        """
        agent_id = agent_json.get("agent_id") or str(uuid.uuid4())
        metadata = agent_json.get("metadata", {})
        security = agent_json.get("security_handshake", {})
        
        name = metadata.get("name", "Unknown")
        provider = metadata.get("provider", "Unknown")
        tier = security.get("auth_tier", "Standard")
        public_key = security.get("public_key")
        status = agent_json.get("status", "Active")
        
        # Flatten capability scope
        caps = [c.get("tool_name") for c in agent_json.get("capabilities", [])]
        auth_scope = ", ".join(caps)
        
        record = {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "name": name,
            "provider": provider,
            "tier": tier,
            "auth_scope": auth_scope,
            "public_key": public_key,
            "status": status,
            "full_schema_json": agent_json # JSONB in Postgres
        }
        
        if self.supabase:
            data, count = self.supabase.table("agents").upsert(record).execute()
            logger.info(f"Registered Agent {agent_id} for Tenant {tenant_id}")
            return agent_id
        
        return "mock-id"

    def add_rule(self, natural_language: str, logic_json: dict, tenant_id: str, priority=1) -> Any:
        rule_id = str(uuid.uuid4())
        status = "Active"
        
        record = {
            "rule_id": rule_id,
            "tenant_id": tenant_id,
            "natural_language": natural_language,
            "logic_json": logic_json, # JSONB
            "priority": priority,
            "status": status,
            "created_at": datetime.datetime.now().isoformat()
        }
        
        if self.supabase:
            # 1. Write to Postgres
            self.supabase.table("rules").insert(record).execute()
            
            # 2. Update Local Redis Cache (Hot-Loading)
            # Pub/Sub notification
            msg = {"type": "RULE_ADDED", "data": record}
            self.redis.publish("registry_updates", json.dumps(msg))
            
            # Update Bloom Filter
            bf_key = "rules:bf"
            item = f"{tenant_id}:{rule_id}"
            self.redis.bf().add(bf_key, item)
            
            logger.info(f"Added Rule {rule_id} for Tenant {tenant_id}")
            
        return rule_id

    def get_agent_profile(self, agent_id: str, tenant_id: str) -> None:
        if not self.supabase:
            return None
            
        # RLS compliant query
        response = self.supabase.table("agents").select("full_schema_json")\
            .eq("agent_id", agent_id)\
            .eq("tenant_id", tenant_id)\
            .execute()
            
        if response.data:
            profile = response.data[0]["full_schema_json"]
            # Inject Usage Policy (Cognitive Contract)
            gov_header = (
                "You are operating under the OCX (Operational Control Plane). "
                "Every action you take is audited by The Jury for Factuality, Compliance, and Logic. "
                "If your Trust Score falls below 70%, your session will be terminated."
            )
            if "system_prompt" in profile:
                profile["system_prompt"] = gov_header + "\n\n" + profile["system_prompt"]
            else:
                profile["system_prompt"] = gov_header
            return profile
            
        return None

    def check_rule_existence(self, rule_id: str, tenant_id: str) -> bool:
        """
        Fast Bloom Filter check.
        """
        bf_key = "rules:bf"
        item = f"{tenant_id}:{rule_id}"
        # If returns 0, definitely doesn't exist. If 1, maybe exists (check DB).
        return bool(self.redis.bf().exists(bf_key, item))

    def eject_agent(self, agent_id: str, tenant_id: str) -> bool:
        """
        Kill Switch: Immediately revokes an agent's access tokens and sets status to 'EJECTED'.
        Propagates to Redis for instant blocking by other services.
        """
        logger.warning(f"🚨 KILL SWITCH ACTIVATED for Agent {agent_id} (Tenant: {tenant_id})")
        
        # 1. Update Persistent Store (Supabase)
        if self.supabase:
            self.supabase.table("agents").update({"status": "EJECTED"}).eq("agent_id", agent_id).eq("tenant_id", tenant_id).execute()
            
        # 2. Instant Cache Invalidation (Redis)
        # We publish to a 'kill_switch' channel that Gateways/PolicyEngines subscribe to
        msg = {"type": "AGENT_EJECTED", "agent_id": agent_id, "tenant_id": tenant_id}
        self.redis.publish("registry_updates", json.dumps(msg))
        
        # 3. Add to Blacklist Bloom Filter (if we had one separate for revoked, but usually status check covers it)
        # For immediate block, we set a specific key
        block_key = f"block:agent:{tenant_id}:{agent_id}"
        self.redis.setex(block_key, 3600, "1") # Block for 1 hour explicitly in hot cache
        
        return True

    # ... (Other methods like get_raci can remain similar but using Supabase) ...
