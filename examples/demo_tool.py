from ocx_sdk import BaseOCXTool, SecurityError

class SecureDatabaseTool(BaseOCXTool):
    name = "secure_db_query"
    description = "Executes a secure database query."

    def run_impl(self, query: str) -> str:
        # This logic only runs if trust is granted
        return f"Query Results for: {query}"

if __name__ == "__main__":
    print("--- SDK Demo: Secure Tool Execution (Signed) ---")
    
    # Initialize tool (generates new ECDSA keypair)
    tool = SecureDatabaseTool()
    print(f"🔑 Identity: {tool.agent_id[:16]}...")
    
    # Context (simulating runtime metadata)
    ctx = {"user_role": "admin", "region": "us-east-1"}
    
    try:
        # We call .run(), which now Signs the payload
        result = tool.run(query="SELECT * FROM vital_records")
        print(f"Output: {result}")
    except SecurityError as e:
        print(f"Blocked: {e}")
    except Exception as e:
        import traceback
        traceback.print_exc()
