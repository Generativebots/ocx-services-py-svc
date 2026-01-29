"""
JSON-Logic Enforcement Engine
Implements full JSON-Logic standard for policy evaluation
"""

from typing import Any, Dict, List, Optional
import json_logic


class JSONLogicEngine:
    """
    Evaluates JSON-Logic expressions against data payloads
    Supports: and, or, not, in, >, <, >=, <=, ==, !=, var
    """
    
    def __init__(self):
        # Pre-compile common logic patterns for performance
        self._cache: Dict[str, Any] = {}
    
    def evaluate(
        self,
        logic: Dict[str, Any],
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Evaluate JSON-Logic expression against data
        
        Args:
            logic: JSON-Logic expression (e.g., {"and": [...]})
            data: Data payload to evaluate against
            context: Additional context (whitelist, pre-approved lists, etc.)
            
        Returns:
            True if logic passes, False otherwise
            
        Example:
            logic = {"and": [
                {">": [{"var": "amount"}, 500]},
                {"not": {"in": [{"var": "vendor"}, ["APPROVED_1"]]}}
            ]}
            data = {"amount": 1000, "vendor": "UNKNOWN"}
            result = engine.evaluate(logic, data)  # True (violation)
        """
        # Merge context into data
        if context:
            data = {**data, **context}
        
        try:
            result = json_logic.jsonLogic(logic, data)
            return bool(result)
        except Exception as e:
            print(f"❌ JSON-Logic evaluation failed: {e}")
            print(f"   Logic: {logic}")
            print(f"   Data: {data}")
            # Fail-closed on evaluation errors
            return False
    
    def validate_logic(self, logic: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate JSON-Logic syntax
        
        Returns:
            (is_valid, error_message)
        """
        try:
            # Test with empty data
            json_logic.jsonLogic(logic, {})
            return True, None
        except Exception as e:
            return False, str(e)
    
    def extract_variables(self, logic: Dict[str, Any]) -> List[str]:
        """
        Extract all variable names from JSON-Logic expression
        
        Example:
            logic = {">": [{"var": "payload.amount"}, 500]}
            result = ["payload.amount"]
        """
        variables = []
        
        def traverse(obj):
            if isinstance(obj, dict):
                if "var" in obj:
                    variables.append(obj["var"])
                for value in obj.values():
                    traverse(value)
            elif isinstance(obj, list):
                for item in obj:
                    traverse(item)
        
        traverse(logic)
        return list(set(variables))  # Deduplicate
    
    def simplify(self, logic: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simplify JSON-Logic expression (remove redundant operations)
        
        Example:
            {"and": [{"==": [1, 1]}]} → {"==": [1, 1]}
        """
        # TODO: Implement logic simplification
        # For now, return as-is
        return logic


# Example usage and test cases
if __name__ == "__main__":
    engine = JSONLogicEngine()
    
    # Test 1: Simple comparison
    logic1 = {">": [{"var": "amount"}, 500]}
    data1 = {"amount": 1000}
    print(f"Test 1: {engine.evaluate(logic1, data1)}")  # True
    
    # Test 2: Complex AND with NOT
    logic2 = {
        "and": [
            {">": [{"var": "payload.amount"}, 500]},
            {"not": {"in": [{"var": "payload.vendor_id"}, ["APPROVED_1", "APPROVED_2"]]}}
        ]
    }
    data2 = {"payload": {"amount": 1000, "vendor_id": "UNKNOWN"}}
    print(f"Test 2: {engine.evaluate(logic2, data2)}")  # True (violation)
    
    # Test 3: With context (whitelist)
    logic3 = {"in": [{"var": "destination"}, {"var": "whitelist.endpoints"}]}
    data3 = {"destination": "https://api.example.com"}
    context3 = {"whitelist": {"endpoints": ["https://api.example.com", "https://api.trusted.com"]}}
    print(f"Test 3: {engine.evaluate(logic3, data3, context3)}")  # True (allowed)
    
    # Test 4: Variable extraction
    variables = engine.extract_variables(logic2)
    print(f"Variables: {variables}")  # ['payload.amount', 'payload.vendor_id']
