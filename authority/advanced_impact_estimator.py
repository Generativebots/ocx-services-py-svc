"""
Advanced Impact Estimation with Customization
User-editable assumptions, industry templates, sensitivity analysis, Monte Carlo simulation
"""

import json
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
import logging
logger = logging.getLogger(__name__)


class Industry(Enum):
    """Industry templates"""
    FINANCIAL_SERVICES = "financial_services"
    HEALTHCARE = "healthcare"
    MANUFACTURING = "manufacturing"
    RETAIL = "retail"
    TECHNOLOGY = "technology"
    GOVERNMENT = "government"


@dataclass
class ImpactAssumptions:
    """User-editable assumptions for impact calculation"""
    # Time savings
    avg_time_saved_per_transaction_minutes: float = 5.0
    transactions_per_day: int = 100
    working_days_per_year: int = 250
    hourly_labor_cost: float = 50.0
    
    # Error reduction
    current_error_rate: float = 0.05  # 5%
    target_error_rate: float = 0.01   # 1%
    avg_cost_per_error: float = 500.0
    
    # Trust tax
    current_trust_level: float = 0.5
    target_trust_level: float = 0.85
    base_trust_tax_rate: float = 0.10
    transaction_value: float = 10000.0
    
    # Growth
    adoption_rate_year1: float = 0.25  # 25%
    adoption_rate_year2: float = 0.50  # 50%
    adoption_rate_year3: float = 0.75  # 75%
    
    # Risk factors
    implementation_risk: float = 0.15  # 15% chance of delay
    integration_complexity: float = 0.5  # 0-1 scale
    change_management_risk: float = 0.20  # 20% resistance
    
    # Costs
    implementation_cost: float = 100000.0
    annual_maintenance_cost: float = 20000.0
    training_cost_per_user: float = 500.0
    number_of_users: int = 50


class AdvancedImpactEstimator:
    """Advanced impact estimator with customization and Monte Carlo simulation"""
    
    def __init__(self, db_conn) -> None:
        self.db_conn = db_conn
        self._init_tables()
        self._load_industry_templates()
    
    def _init_tables(self) -> None:
        """Initialize tables for custom assumptions"""
        with self.db_conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS impact_assumptions (
                    assumption_id VARCHAR(255) PRIMARY KEY,
                    company_id VARCHAR(255),
                    use_case_id VARCHAR(255),
                    assumptions JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS impact_simulations (
                    simulation_id VARCHAR(255) PRIMARY KEY,
                    company_id VARCHAR(255),
                    use_case_id VARCHAR(255),
                    assumptions JSONB,
                    results JSONB,
                    num_iterations INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.db_conn.commit()
    
    def _load_industry_templates(self) -> None:
        """Load industry-specific templates"""
        self.industry_templates = {
            Industry.FINANCIAL_SERVICES: ImpactAssumptions(
                avg_time_saved_per_transaction_minutes=3.0,
                transactions_per_day=500,
                hourly_labor_cost=75.0,
                current_error_rate=0.02,
                target_error_rate=0.005,
                avg_cost_per_error=2000.0,
                transaction_value=50000.0
            ),
            Industry.HEALTHCARE: ImpactAssumptions(
                avg_time_saved_per_transaction_minutes=10.0,
                transactions_per_day=50,
                hourly_labor_cost=60.0,
                current_error_rate=0.03,
                target_error_rate=0.005,
                avg_cost_per_error=5000.0,
                transaction_value=5000.0
            ),
            Industry.MANUFACTURING: ImpactAssumptions(
                avg_time_saved_per_transaction_minutes=15.0,
                transactions_per_day=200,
                hourly_labor_cost=40.0,
                current_error_rate=0.08,
                target_error_rate=0.02,
                avg_cost_per_error=1000.0,
                transaction_value=15000.0
            ),
            Industry.RETAIL: ImpactAssumptions(
                avg_time_saved_per_transaction_minutes=2.0,
                transactions_per_day=1000,
                hourly_labor_cost=25.0,
                current_error_rate=0.10,
                target_error_rate=0.03,
                avg_cost_per_error=100.0,
                transaction_value=500.0
            ),
            Industry.TECHNOLOGY: ImpactAssumptions(
                avg_time_saved_per_transaction_minutes=8.0,
                transactions_per_day=150,
                hourly_labor_cost=100.0,
                current_error_rate=0.04,
                target_error_rate=0.01,
                avg_cost_per_error=3000.0,
                transaction_value=25000.0
            ),
            Industry.GOVERNMENT: ImpactAssumptions(
                avg_time_saved_per_transaction_minutes=20.0,
                transactions_per_day=30,
                hourly_labor_cost=50.0,
                current_error_rate=0.15,
                target_error_rate=0.05,
                avg_cost_per_error=10000.0,
                transaction_value=10000.0
            )
        }
    
    def get_industry_template(self, industry: str) -> ImpactAssumptions:
        """Get industry-specific template"""
        try:
            industry_enum = Industry(industry)
            return self.industry_templates[industry_enum]
        except (ValueError, KeyError):
            return ImpactAssumptions()  # Default
    
    def calculate_impact(
        self,
        assumptions: ImpactAssumptions,
        years: int = 3
    ) -> Dict[str, Any]:
        """Calculate business impact with custom assumptions"""
        
        # Time savings
        annual_time_saved_hours = (
            assumptions.avg_time_saved_per_transaction_minutes / 60 *
            assumptions.transactions_per_day *
            assumptions.working_days_per_year
        )
        annual_labor_savings = annual_time_saved_hours * assumptions.hourly_labor_cost
        
        # Error reduction
        error_reduction = assumptions.current_error_rate - assumptions.target_error_rate
        annual_errors_prevented = (
            error_reduction *
            assumptions.transactions_per_day *
            assumptions.working_days_per_year
        )
        annual_error_savings = annual_errors_prevented * assumptions.avg_cost_per_error
        
        # Trust tax savings
        current_tax = (1.0 - assumptions.current_trust_level) * assumptions.base_trust_tax_rate
        target_tax = (1.0 - assumptions.target_trust_level) * assumptions.base_trust_tax_rate
        tax_savings_per_transaction = (current_tax - target_tax) * assumptions.transaction_value
        annual_tax_savings = (
            tax_savings_per_transaction *
            assumptions.transactions_per_day *
            assumptions.working_days_per_year
        )
        
        # Total annual benefits
        total_annual_benefits = (
            annual_labor_savings +
            annual_error_savings +
            annual_tax_savings
        )
        
        # Costs
        total_implementation_cost = (
            assumptions.implementation_cost +
            (assumptions.training_cost_per_user * assumptions.number_of_users)
        )
        
        # Year-by-year projection
        yearly_projections = []
        cumulative_benefits = 0
        cumulative_costs = total_implementation_cost
        
        for year in range(1, years + 1):
            if year == 1:
                adoption_rate = assumptions.adoption_rate_year1
            elif year == 2:
                adoption_rate = assumptions.adoption_rate_year2
            else:
                adoption_rate = assumptions.adoption_rate_year3
            
            year_benefits = total_annual_benefits * adoption_rate
            year_costs = assumptions.annual_maintenance_cost
            
            cumulative_benefits += year_benefits
            cumulative_costs += year_costs
            
            net_benefit = cumulative_benefits - cumulative_costs
            roi = (net_benefit / cumulative_costs) * 100 if cumulative_costs > 0 else 0
            
            yearly_projections.append({
                "year": year,
                "adoption_rate": adoption_rate,
                "benefits": year_benefits,
                "costs": year_costs,
                "cumulative_benefits": cumulative_benefits,
                "cumulative_costs": cumulative_costs,
                "net_benefit": net_benefit,
                "roi": roi
            })
        
        # Payback period
        payback_period = None
        for proj in yearly_projections:
            if proj["net_benefit"] >= 0:
                payback_period = proj["year"]
                break
        
        return {
            "annual_labor_savings": annual_labor_savings,
            "annual_error_savings": annual_error_savings,
            "annual_tax_savings": annual_tax_savings,
            "total_annual_benefits": total_annual_benefits,
            "implementation_cost": total_implementation_cost,
            "annual_maintenance_cost": assumptions.annual_maintenance_cost,
            "yearly_projections": yearly_projections,
            "payback_period_years": payback_period,
            "three_year_roi": yearly_projections[-1]["roi"] if yearly_projections else 0
        }
    
    def sensitivity_analysis(
        self,
        base_assumptions: ImpactAssumptions,
        variables: List[str],
        variation_percent: float = 0.20  # ±20%
    ) -> Dict[str, Any]:
        """
        Perform sensitivity analysis on key variables
        Shows how changes in assumptions affect ROI
        """
        results = {}
        
        for variable in variables:
            if not hasattr(base_assumptions, variable):
                continue
            
            base_value = getattr(base_assumptions, variable)
            
            # Test low, base, and high scenarios
            scenarios = {
                "low": base_value * (1 - variation_percent),
                "base": base_value,
                "high": base_value * (1 + variation_percent)
            }
            
            scenario_results = {}
            
            for scenario_name, value in scenarios.items():
                # Create modified assumptions
                modified = ImpactAssumptions(**asdict(base_assumptions))
                setattr(modified, variable, value)
                
                # Calculate impact
                impact = self.calculate_impact(modified)
                
                scenario_results[scenario_name] = {
                    "value": value,
                    "roi": impact["three_year_roi"],
                    "payback_period": impact["payback_period_years"]
                }
            
            # Calculate sensitivity
            roi_range = scenario_results["high"]["roi"] - scenario_results["low"]["roi"]
            sensitivity = roi_range / (2 * variation_percent * 100)  # Normalized
            
            results[variable] = {
                "scenarios": scenario_results,
                "sensitivity": sensitivity,
                "impact": "high" if abs(sensitivity) > 1.0 else "medium" if abs(sensitivity) > 0.5 else "low"
            }
        
        return results
    
    def monte_carlo_simulation(
        self,
        base_assumptions: ImpactAssumptions,
        num_iterations: int = 10000,
        risk_factors: Optional[Dict[str, tuple]] = None
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo simulation for risk analysis
        Returns distribution of possible outcomes
        """
        if risk_factors is None:
            # Default risk factors (variable: (mean, std_dev))
            risk_factors = {
                "avg_time_saved_per_transaction_minutes": (base_assumptions.avg_time_saved_per_transaction_minutes, 1.0),
                "transactions_per_day": (base_assumptions.transactions_per_day, 20),
                "current_error_rate": (base_assumptions.current_error_rate, 0.01),
                "implementation_cost": (base_assumptions.implementation_cost, 20000),
                "adoption_rate_year1": (base_assumptions.adoption_rate_year1, 0.05),
            }
        
        roi_results = []
        payback_results = []
        
        for _ in range(num_iterations):
            # Create randomized assumptions
            simulated = ImpactAssumptions(**asdict(base_assumptions))
            
            for variable, (mean, std_dev) in risk_factors.items():
                if hasattr(simulated, variable):
                    # Generate random value from normal distribution
                    value = np.random.normal(mean, std_dev)
                    
                    # Ensure positive values and reasonable bounds
                    if "rate" in variable:
                        value = max(0.0, min(1.0, value))
                    else:
                        value = max(0.0, value)
                    
                    setattr(simulated, variable, value)
            
            # Calculate impact
            impact = self.calculate_impact(simulated)
            
            roi_results.append(impact["three_year_roi"])
            payback_results.append(impact["payback_period_years"] if impact["payback_period_years"] else 999)
        
        # Calculate statistics
        roi_array = np.array(roi_results)
        payback_array = np.array([p for p in payback_results if p < 999])
        
        return {
            "num_iterations": num_iterations,
            "roi": {
                "mean": float(np.mean(roi_array)),
                "median": float(np.median(roi_array)),
                "std_dev": float(np.std(roi_array)),
                "min": float(np.min(roi_array)),
                "max": float(np.max(roi_array)),
                "p10": float(np.percentile(roi_array, 10)),
                "p25": float(np.percentile(roi_array, 25)),
                "p75": float(np.percentile(roi_array, 75)),
                "p90": float(np.percentile(roi_array, 90)),
                "probability_positive": float(np.sum(roi_array > 0) / len(roi_array))
            },
            "payback_period": {
                "mean": float(np.mean(payback_array)) if len(payback_array) > 0 else None,
                "median": float(np.median(payback_array)) if len(payback_array) > 0 else None,
                "probability_within_3_years": float(np.sum(payback_array <= 3) / num_iterations)
            }
        }
    
    def save_assumptions(
        self,
        company_id: str,
        use_case_id: str,
        assumptions: ImpactAssumptions
    ) -> str:
        """Save custom assumptions"""
        import uuid
        
        assumption_id = f"assum_{uuid.uuid4().hex[:12]}"
        
        with self.db_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO impact_assumptions (
                    assumption_id, company_id, use_case_id, assumptions
                ) VALUES (%s, %s, %s, %s)
            """, (
                assumption_id,
                company_id,
                use_case_id,
                json.dumps(asdict(assumptions))
            ))
            self.db_conn.commit()
        
        return assumption_id
    
    def save_simulation(
        self,
        company_id: str,
        use_case_id: str,
        assumptions: ImpactAssumptions,
        results: Dict[str, Any],
        num_iterations: int
    ) -> str:
        """Save Monte Carlo simulation results"""
        import uuid

        
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
        
        with self.db_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO impact_simulations (
                    simulation_id, company_id, use_case_id, assumptions, results, num_iterations
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                simulation_id,
                company_id,
                use_case_id,
                json.dumps(asdict(assumptions)),
                json.dumps(results),
                num_iterations
            ))
            self.db_conn.commit()
        
        return simulation_id
