"""
Trust Tax Engine - Micro-Transaction Billing for Cross-Sovereign Trust

Charges $0.01 per trust verification event, with dynamic pricing based on trust level.
Aggregates micro-transactions for monthly billing.
"""

import uuid
from datetime import datetime
from typing import Dict, List
from decimal import Decimal

from google.cloud import spanner
from google.cloud.spanner_v1 import param_types


class TrustTaxEngine:
    """
    Micro-transaction engine for trust verification events.
    
    Pricing Model:
    - Base rate: $0.01 per trust event
    - Dynamic pricing: fee × (1.0 / trust_level)
    - Lower trust = higher fee (incentivizes trust building)
    
    Revenue Model:
    - 10M transactions/day @ $0.015 avg = $150K/day = $54.75M/year
    """
    
    BASE_RATE = 0.01  # $0.01 per trust event
    
    def __init__(self, instance_id: str, database_id: str):
        """
        Initialize Trust Tax Engine.
        
        Args:
            instance_id: Cloud Spanner instance ID
            database_id: Cloud Spanner database ID
        """
        self.spanner_client = spanner.Client()
        self.instance = self.spanner_client.instance(instance_id)
        self.database = self.instance.database(database_id)
    
    def charge_trust_event(self, local_ocx: str, remote_ocx: str, agent_id: str, trust_level: float) -> Dict:
        """
        Charge for a trust verification event.
        
        Args:
            local_ocx: Local OCX instance ID
            remote_ocx: Remote OCX instance ID
            agent_id: Agent identifier
            trust_level: Trust level (0.0 to 1.0)
        
        Returns:
            Dict: Transaction record
        """
        # 1. Calculate dynamic fee
        if trust_level <= 0:
            trust_level = 0.1  # Minimum to avoid division by zero
        
        dynamic_fee = self.BASE_RATE * (1.0 / trust_level)
        
        # 2. Create transaction record
        transaction_id = str(uuid.uuid4())
        billing_month = datetime.utcnow().strftime('%Y-%m')
        
        transaction = {
            'transaction_id': transaction_id,
            'local_ocx': local_ocx,
            'remote_ocx': remote_ocx,
            'agent_id': agent_id,
            'trust_level': trust_level,
            'base_fee_usd': self.BASE_RATE,
            'dynamic_fee_usd': dynamic_fee,
            'timestamp': spanner.COMMIT_TIMESTAMP,
            'billing_month': billing_month,
        }
        
        # 3. Insert transaction
        with self.database.batch() as batch:
            batch.insert(
                table='trust_tax_transactions',
                columns=list(transaction.keys()),
                values=[list(transaction.values())]
            )
        
        # 4. Update monthly aggregate
        self._update_monthly_bill(local_ocx, billing_month, dynamic_fee)
        
        print(f"💰 Trust tax charged: ${dynamic_fee:.4f} (trust: {trust_level:.2f}, agent: {agent_id})")
        
        return transaction
    
    def _update_monthly_bill(self, ocx_instance_id: str, billing_month: str, fee: float):
        """
        Update monthly billing aggregate.
        
        Args:
            ocx_instance_id: OCX instance ID
            billing_month: Billing month (YYYY-MM)
            fee: Fee to add
        """
        # Use Spanner's DML for atomic update
        update_query = """
            UPDATE trust_tax_monthly_bills
            SET total_transactions = total_transactions + 1,
                total_fee_usd = total_fee_usd + @fee
            WHERE ocx_instance_id = @ocx_instance_id
              AND billing_month = @billing_month
        """
        
        params = {
            'ocx_instance_id': ocx_instance_id,
            'billing_month': billing_month,
            'fee': fee,
        }
        
        param_types_dict = {
            'ocx_instance_id': param_types.STRING,
            'billing_month': param_types.STRING,
            'fee': param_types.FLOAT64,
        }
        
        def update_bill(transaction):
            row_count = transaction.execute_update(
                update_query,
                params=params,
                param_types=param_types_dict
            )
            
            # If no row updated, insert new bill
            if row_count == 0:
                bill_id = str(uuid.uuid4())
                transaction.insert(
                    table='trust_tax_monthly_bills',
                    columns=['bill_id', 'ocx_instance_id', 'billing_month', 
                            'total_transactions', 'total_fee_usd', 'avg_trust_level', 
                            'created_at', 'paid'],
                    values=[[bill_id, ocx_instance_id, billing_month, 1, fee, 0.0, 
                            spanner.COMMIT_TIMESTAMP, False]]
                )
        
        self.database.run_in_transaction(update_bill)
    
    def get_monthly_bill(self, ocx_instance_id: str, billing_month: str) -> Dict:
        """
        Get monthly bill for an OCX instance.
        
        Args:
            ocx_instance_id: OCX instance ID
            billing_month: Billing month (YYYY-MM)
        
        Returns:
            Dict: Bill details
        """
        query = """
            SELECT bill_id, total_transactions, total_fee_usd, avg_trust_level, 
                   created_at, paid, paid_at
            FROM trust_tax_monthly_bills
            WHERE ocx_instance_id = @ocx_instance_id
              AND billing_month = @billing_month
        """
        
        params = {
            'ocx_instance_id': ocx_instance_id,
            'billing_month': billing_month,
        }
        
        param_types_dict = {
            'ocx_instance_id': param_types.STRING,
            'billing_month': param_types.STRING,
        }
        
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                query,
                params=params,
                param_types=param_types_dict
            )
            
            rows = list(results)
            if not rows:
                return None
            
            row = rows[0]
            return {
                'bill_id': row[0],
                'ocx_instance_id': ocx_instance_id,
                'billing_month': billing_month,
                'total_transactions': row[1],
                'total_fee_usd': row[2],
                'avg_trust_level': row[3],
                'created_at': row[4],
                'paid': row[5],
                'paid_at': row[6],
            }
    
    def mark_bill_paid(self, bill_id: str) -> bool:
        """
        Mark a bill as paid.
        
        Args:
            bill_id: Bill ID
        
        Returns:
            bool: True if successful
        """
        update_query = """
            UPDATE trust_tax_monthly_bills
            SET paid = true,
                paid_at = CURRENT_TIMESTAMP()
            WHERE bill_id = @bill_id
        """
        
        params = {'bill_id': bill_id}
        param_types_dict = {'bill_id': param_types.STRING}
        
        def mark_paid(transaction):
            transaction.execute_update(
                update_query,
                params=params,
                param_types=param_types_dict
            )
        
        self.database.run_in_transaction(mark_paid)
        print(f"✅ Bill marked as paid: {bill_id}")
        return True
    
    def get_transaction_history(self, ocx_instance_id: str, limit: int = 100) -> List[Dict]:
        """
        Get transaction history for an OCX instance.
        
        Args:
            ocx_instance_id: OCX instance ID
            limit: Maximum number of transactions
        
        Returns:
            List[Dict]: Transaction records
        """
        query = """
            SELECT transaction_id, local_ocx, remote_ocx, agent_id, 
                   trust_level, base_fee_usd, dynamic_fee_usd, timestamp
            FROM trust_tax_transactions
            WHERE local_ocx = @ocx_instance_id
            ORDER BY timestamp DESC
            LIMIT @limit
        """
        
        params = {
            'ocx_instance_id': ocx_instance_id,
            'limit': limit,
        }
        
        param_types_dict = {
            'ocx_instance_id': param_types.STRING,
            'limit': param_types.INT64,
        }
        
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                query,
                params=params,
                param_types=param_types_dict
            )
            
            transactions = []
            for row in results:
                transactions.append({
                    'transaction_id': row[0],
                    'local_ocx': row[1],
                    'remote_ocx': row[2],
                    'agent_id': row[3],
                    'trust_level': row[4],
                    'base_fee_usd': row[5],
                    'dynamic_fee_usd': row[6],
                    'timestamp': row[7],
                })
        
        return transactions
    
    def get_revenue_analytics(self, start_month: str, end_month: str) -> Dict:
        """
        Get revenue analytics across all OCX instances.
        
        Args:
            start_month: Start month (YYYY-MM)
            end_month: End month (YYYY-MM)
        
        Returns:
            Dict: Revenue analytics
        """
        query = """
            SELECT 
                COUNT(*) as total_bills,
                SUM(total_transactions) as total_transactions,
                SUM(total_fee_usd) as total_revenue,
                AVG(total_fee_usd) as avg_bill_amount,
                COUNT(CASE WHEN paid THEN 1 END) as paid_bills
            FROM trust_tax_monthly_bills
            WHERE billing_month >= @start_month
              AND billing_month <= @end_month
        """
        
        params = {
            'start_month': start_month,
            'end_month': end_month,
        }
        
        param_types_dict = {
            'start_month': param_types.STRING,
            'end_month': param_types.STRING,
        }
        
        with self.database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                query,
                params=params,
                param_types=param_types_dict
            )
            
            row = list(results)[0]
        
        return {
            'total_bills': row[0],
            'total_transactions': row[1],
            'total_revenue_usd': row[2],
            'avg_bill_amount_usd': row[3],
            'paid_bills': row[4],
            'payment_rate': row[4] / row[0] if row[0] > 0 else 0,
        }


# Example usage
if __name__ == "__main__":
    engine = TrustTaxEngine(
        instance_id="ocx-trust-ledger",
        database_id="trust-attestations"
    )
    
    # Charge trust event
    transaction = engine.charge_trust_event(
        local_ocx="ocx-us-west1-001",
        remote_ocx="ocx-eu-west1-002",
        agent_id="AGENT_001",
        trust_level=0.85
    )
    
    print(f"Transaction: {transaction}")
    
    # Get monthly bill
    bill = engine.get_monthly_bill("ocx-us-west1-001", "2026-01")
    print(f"Monthly bill: {bill}")
    
    # Get revenue analytics
    analytics = engine.get_revenue_analytics("2026-01", "2026-01")
    print(f"Revenue analytics: {analytics}")
