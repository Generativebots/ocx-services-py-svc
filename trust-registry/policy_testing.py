"""
Policy Testing Framework
Generates test cases, simulates policies, and runs regression tests
"""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from json_logic_engine import JSONLogicEngine
from policy_hierarchy import Policy, PolicyTier


@dataclass
class TestCase:
    """Represents a policy test case"""
    name: str
    policy_id: str
    input_data: Dict[str, Any]
    expected_result: bool  # True = allow, False = block
    expected_action: str
    description: str


@dataclass
class TestResult:
    """Result of a test case execution"""
    test_case: TestCase
    actual_result: bool
    actual_action: str
    passed: bool
    error: Optional[str] = None


class PolicyTestGenerator:
    """Generates test cases for policies"""
    
    def __init__(self):
        self.logic_engine = JSONLogicEngine()
    
    def generate_test_cases(self, policy: Dict[str, Any]) -> List[TestCase]:
        """
        Generate test cases for a policy
        
        Generates:
        1. Positive case (should pass)
        2. Negative case (should fail)
        3. Edge cases (boundary values)
        """
        test_cases = []
        policy_id = policy.get("policy_id", "unknown")
        logic = policy.get("logic", {})
        action = policy.get("action", {})
        
        # Extract variables
        variables = self.logic_engine.extract_variables(logic)
        
        # Generate positive case (should ALLOW)
        positive_data = self._generate_positive_case(logic, variables)
        test_cases.append(TestCase(
            name=f"{policy_id}_positive",
            policy_id=policy_id,
            input_data=positive_data,
            expected_result=True,
            expected_action=action.get("on_pass", "ALLOW"),
            description="Should pass policy validation"
        ))
        
        # Generate negative case (should BLOCK)
        negative_data = self._generate_negative_case(logic, variables)
        test_cases.append(TestCase(
            name=f"{policy_id}_negative",
            policy_id=policy_id,
            input_data=negative_data,
            expected_result=False,
            expected_action=action.get("on_fail", "BLOCK"),
            description="Should violate policy"
        ))
        
        # Generate edge cases
        edge_cases = self._generate_edge_cases(logic, variables)
        for i, edge_data in enumerate(edge_cases):
            test_cases.append(TestCase(
                name=f"{policy_id}_edge_{i}",
                policy_id=policy_id,
                input_data=edge_data,
                expected_result=False,  # Assume edge cases violate
                expected_action=action.get("on_fail", "BLOCK"),
                description=f"Edge case {i}: boundary value"
            ))
        
        return test_cases
    
    def _generate_positive_case(
        self,
        logic: Dict[str, Any],
        variables: List[str]
    ) -> Dict[str, Any]:
        """Generate data that should pass the policy"""
        data = {}
        
        for var in variables:
            if "amount" in var.lower():
                data[var] = 100  # Below typical thresholds
            elif "vendor" in var.lower():
                data[var] = "APPROVED_VENDOR"
            else:
                data[var] = "safe_value"
        
        return data
    
    def _generate_negative_case(
        self,
        logic: Dict[str, Any],
        variables: List[str]
    ) -> Dict[str, Any]:
        """Generate data that should violate the policy"""
        data = {}
        
        for var in variables:
            if "amount" in var.lower():
                data[var] = 10000  # Above typical thresholds
            elif "vendor" in var.lower():
                data[var] = "UNKNOWN_VENDOR"
            else:
                data[var] = "unsafe_value"
        
        return data
    
    def _generate_edge_cases(
        self,
        logic: Dict[str, Any],
        variables: List[str]
    ) -> List[Dict[str, Any]]:
        """Generate edge case data (boundary values)"""
        edge_cases = []
        
        for var in variables:
            if "amount" in var.lower():
                # Test exactly at threshold
                edge_cases.append({var: 500})
                edge_cases.append({var: 501})
                edge_cases.append({var: 499})
        
        return edge_cases


class PolicySimulator:
    """Simulates policy execution"""
    
    def __init__(self):
        self.logic_engine = JSONLogicEngine()
    
    def run_test(
        self,
        policy: Dict[str, Any],
        test_case: TestCase
    ) -> TestResult:
        """
        Run a single test case against a policy
        
        Returns:
            TestResult with pass/fail status
        """
        try:
            # Evaluate policy
            violates = self.logic_engine.evaluate(
                policy.get("logic", {}),
                test_case.input_data
            )
            
            actual_result = not violates  # True = allowed
            actual_action = policy.get("action", {}).get(
                "on_fail" if violates else "on_pass",
                "BLOCK" if violates else "ALLOW"
            )
            
            # Check if test passed
            passed = (
                actual_result == test_case.expected_result and
                actual_action == test_case.expected_action
            )
            
            return TestResult(
                test_case=test_case,
                actual_result=actual_result,
                actual_action=actual_action,
                passed=passed
            )
            
        except Exception as e:
            return TestResult(
                test_case=test_case,
                actual_result=False,
                actual_action="ERROR",
                passed=False,
                error=str(e)
            )
    
    def run_test_suite(
        self,
        policy: Dict[str, Any],
        test_cases: List[TestCase]
    ) -> List[TestResult]:
        """Run all test cases for a policy"""
        results = []
        for test_case in test_cases:
            result = self.run_test(policy, test_case)
            results.append(result)
        return results


class RegressionTester:
    """Runs regression tests on policy changes"""
    
    def __init__(self):
        self.simulator = PolicySimulator()
        self.test_history: Dict[str, List[TestResult]] = {}
    
    def run_regression(
        self,
        old_policy: Dict[str, Any],
        new_policy: Dict[str, Any],
        test_cases: List[TestCase]
    ) -> Dict[str, Any]:
        """
        Run regression test comparing old vs new policy
        
        Returns:
            Report with differences
        """
        old_results = self.simulator.run_test_suite(old_policy, test_cases)
        new_results = self.simulator.run_test_suite(new_policy, test_cases)
        
        # Compare results
        regressions = []
        improvements = []
        
        for old_res, new_res in zip(old_results, new_results):
            if old_res.passed and not new_res.passed:
                regressions.append({
                    "test_case": old_res.test_case.name,
                    "old_result": old_res.actual_action,
                    "new_result": new_res.actual_action
                })
            elif not old_res.passed and new_res.passed:
                improvements.append({
                    "test_case": old_res.test_case.name,
                    "old_result": old_res.actual_action,
                    "new_result": new_res.actual_action
                })
        
        return {
            "policy_id": new_policy.get("policy_id"),
            "total_tests": len(test_cases),
            "regressions": regressions,
            "improvements": improvements,
            "regression_count": len(regressions),
            "improvement_count": len(improvements)
        }


# Example usage
if __name__ == "__main__":
    # Sample policy
    policy = {
        "policy_id": "PURCHASE_001",
        "logic": {">": [{"var": "amount"}, 500]},
        "action": {"on_fail": "BLOCK", "on_pass": "ALLOW"}
    }
    
    # Generate test cases
    generator = PolicyTestGenerator()
    test_cases = generator.generate_test_cases(policy)
    
    print(f"Generated {len(test_cases)} test cases:")
    for tc in test_cases:
        print(f"  - {tc.name}: {tc.description}")
    
    # Run tests
    simulator = PolicySimulator()
    results = simulator.run_test_suite(policy, test_cases)
    
    print(f"\nTest Results:")
    for result in results:
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"  {status} {result.test_case.name}")
        if not result.passed:
            print(f"    Expected: {result.test_case.expected_action}")
            print(f"    Actual: {result.actual_action}")
    
    # Test regression
    old_policy = policy.copy()
    new_policy = policy.copy()
    new_policy["logic"] = {">": [{"var": "amount"}, 1000]}  # Changed threshold
    
    tester = RegressionTester()
    regression_report = tester.run_regression(old_policy, new_policy, test_cases)
    
    print(f"\nRegression Report:")
    print(f"  Regressions: {regression_report['regression_count']}")
    print(f"  Improvements: {regression_report['improvement_count']}")
