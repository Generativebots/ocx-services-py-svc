"""Business Impact Estimator - ROI calculator"""
from typing import Dict, Any
import uuid

class BusinessImpactEstimator:
    def __init__(self, db_conn):
        self.conn = db_conn
    
    def calculate_impact(self, use_case_id: str, assumptions: Dict[str, Any]) -> Dict[str, Any]:
        # Current costs
        manual_cost = assumptions.get('override_frequency', 0) * assumptions.get('avg_time_per_override', 1) * assumptions.get('hourly_rate', 50)
        error_cost = assumptions.get('error_rate', 0) * assumptions.get('error_cost', 1000)
        delay_cost = assumptions.get('delayed_transactions', 0) * assumptions.get('opportunity_cost', 100)
        current_monthly_cost = manual_cost + error_cost + delay_cost
        
        # A2A savings
        automation_savings = manual_cost * 0.9
        error_reduction = error_cost * 0.7
        speed_improvement = delay_cost * 0.8
        a2a_monthly_savings = automation_savings + error_reduction + speed_improvement
        
        # Net savings
        ocx_monthly_cost = assumptions.get('ocx_monthly_cost', 5000)
        net_monthly_savings = a2a_monthly_savings - ocx_monthly_cost
        annual_roi = (net_monthly_savings * 12) / (ocx_monthly_cost * 12) if ocx_monthly_cost > 0 else 0
        payback_period_months = ocx_monthly_cost / net_monthly_savings if net_monthly_savings > 0 else float('inf')
        
        impact = {
            'use_case_id': use_case_id,
            'current_monthly_cost': round(current_monthly_cost, 2),
            'a2a_monthly_savings': round(a2a_monthly_savings, 2),
            'net_monthly_savings': round(net_monthly_savings, 2),
            'annual_roi': round(annual_roi, 2),
            'payback_period_months': round(payback_period_months, 1),
            'assumptions': assumptions
        }
        
        estimate_id = self._store_estimate(impact)
        impact['estimate_id'] = estimate_id
        return impact
    
    def _store_estimate(self, impact: Dict[str, Any]) -> str:
        cursor = self.conn.cursor()
        estimate_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO business_impact_estimates 
            (estimate_id, use_case_id, company_id, current_monthly_cost,
             a2a_monthly_savings, net_monthly_savings, annual_roi,
             payback_period_months, assumptions)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (estimate_id, impact['use_case_id'], 'company-demo',
              impact['current_monthly_cost'], impact['a2a_monthly_savings'],
              impact['net_monthly_savings'], impact['annual_roi'],
              impact['payback_period_months'], impact['assumptions']))
        self.conn.commit()
        cursor.close()
        return estimate_id
