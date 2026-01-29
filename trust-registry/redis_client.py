import redis
import os

class EnforcementEngine:
    def __init__(self, host='localhost', port=6379, db=0):
        self.r = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        self.enforce_script_sha = self._load_script()

    def _load_script(self):
        script_path = os.path.join(os.path.dirname(__file__), 'lua/enforce_policy.lua')
        try:
            with open(script_path, 'r') as f:
                lua_script = f.read()
            return self.r.script_load(lua_script)
        except Exception as e:
            print(f"Warning: Redis not reachable or script missing. Mocking mode. Error: {e}")
            return None

    def register_policy(self, policy_id: str, threshold: float, action: str, operator: str = ">"):
        """
        Hot-loads a policy into Redis hash.
        """
        try:
            self.r.hset(f"policy:{policy_id}", mapping={
                "threshold": threshold,
                "action_if_exceeded": action,
                "logic_operator": operator
            })
            return True
        except:
            return False

    def authorize_action(self, policy_id: str, attribute: str, value: float) -> str:
        """
        Executes the Lua script atomically.
        """
        if not self.enforce_script_sha:
            # Fallback if Redis is down
            return "ALLOW (Redis Down)"
            
        try:
            result = self.r.evalsha(self.enforce_script_sha, 1, f"policy:{policy_id}", attribute, value)
            return result
        except redis.exceptions.NoScriptError:
            # Reload if flushed
            self.enforce_script_sha = self._load_script()
            return self.authorize_action(policy_id, attribute, value)
        except Exception as e:
            print(f"Enforcement Error: {e}")
            return "ERROR"
