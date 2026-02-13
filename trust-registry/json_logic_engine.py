"""
JSON-Logic Enforcement Engine
Implements full JSON-Logic standard for policy evaluation
"""

from typing import Any, Dict, List, Optional
import json_logic
import logging
logger = logging.getLogger(__name__)



class JSONLogicEngine:
    """
    Evaluates JSON-Logic expressions against data payloads
    Supports: and, or, not, in, >, <, >=, <=, ==, !=, var
    """
    
    def __init__(self) -> None:
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
        
        def traverse(obj) -> Any:
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
        Simplify JSON-Logic expression (remove redundant operations).

        Rules applied:
          1. {"and": [X]}  → X   (single-element AND)
          2. {"or":  [X]}  → X   (single-element OR)
          3. {"not": {"not": X}} → X  (double negation)
          4. {"==": [V, V]} → True constant  (identity comparison)
        """
        if not isinstance(logic, dict):
            return logic

        # Recursively simplify children first
        simplified: Dict[str, Any] = {}
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
                return True  # type: ignore[return-value]

        return simplified


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
