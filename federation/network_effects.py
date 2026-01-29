"""
Network Effects Tracker - Metcalfe's Law Implementation

Tracks network value growth according to Metcalfe's Law: n × (n-1) / 2
Monitors three phases:
- Phase 1: Bilateral (10-20 instances, Months 1-6)
- Phase 2: Industry (100-200 instances, Months 7-12)
- Phase 3: Global (1,000+ instances, Year 2+)
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum


class NetworkPhase(Enum):
    """Network growth phases"""
    BILATERAL = "Bilateral Partnerships"
    INDUSTRY = "Industry Adoption"
    GLOBAL = "Global Network"


class OCXRelationship:
    """Represents a relationship between two OCX instances"""
    
    def __init__(self, instance1_id: str, instance2_id: str):
        self.relationship_id = str(uuid.uuid4())
        self.instance1_id = instance1_id
        self.instance2_id = instance2_id
        self.established_at = datetime.utcnow()
        self.total_interactions = 0
        self.successful_interactions = 0
        self.failed_interactions = 0
        self.total_value_created = 0.0
        self.avg_trust_level = 0.5
        self.last_interaction_at: Optional[datetime] = None
        self.active = True
    
    def record_interaction(self, success: bool, trust_level: float, value_created: float):
        """Record an interaction between the two instances"""
        self.total_interactions += 1
        if success:
            self.successful_interactions += 1
        else:
            self.failed_interactions += 1
        
        self.total_value_created += value_created
        
        # Update average trust level (exponential moving average)
        alpha = 0.2  # Smoothing factor
        self.avg_trust_level = (alpha * trust_level) + ((1 - alpha) * self.avg_trust_level)
        
        self.last_interaction_at = datetime.utcnow()
    
    def to_dict(self) -> Dict:
        return {
            'relationship_id': self.relationship_id,
            'instance1_id': self.instance1_id,
            'instance2_id': self.instance2_id,
            'established_at': self.established_at.isoformat(),
            'total_interactions': self.total_interactions,
            'successful_interactions': self.successful_interactions,
            'failed_interactions': self.failed_interactions,
            'success_rate': self.successful_interactions / self.total_interactions if self.total_interactions > 0 else 0,
            'total_value_created': self.total_value_created,
            'avg_trust_level': self.avg_trust_level,
            'last_interaction_at': self.last_interaction_at.isoformat() if self.last_interaction_at else None,
            'active': self.active,
        }


class NetworkMetrics:
    """Network-wide metrics"""
    
    def __init__(self):
        self.timestamp = datetime.utcnow()
        self.total_instances = 0
        self.active_instances = 0
        self.total_relationships = 0
        self.active_relationships = 0
        self.network_value = 0.0
        self.total_interactions = 0
        self.total_value_created = 0.0
        self.avg_trust_level = 0.0
        self.growth_rate = 0.0
        self.current_phase = NetworkPhase.BILATERAL
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'total_instances': self.total_instances,
            'active_instances': self.active_instances,
            'total_relationships': self.total_relationships,
            'active_relationships': self.active_relationships,
            'network_value': self.network_value,
            'total_interactions': self.total_interactions,
            'total_value_created': self.total_value_created,
            'avg_trust_level': self.avg_trust_level,
            'growth_rate': self.growth_rate,
            'current_phase': self.current_phase.value,
        }


class NetworkEffectsTracker:
    """
    Tracks network effects according to Metcalfe's Law
    
    Network Value = n × (n-1) / 2
    where n = number of active instances
    
    Phases:
    - Phase 1 (Bilateral): 10-20 instances → 45-190 relationships
    - Phase 2 (Industry): 100-200 instances → 4,950-19,900 relationships
    - Phase 3 (Global): 1,000+ instances → 499,500+ relationships
    """
    
    def __init__(self):
        self.instances: Dict[str, Dict] = {}
        self.relationships: Dict[str, OCXRelationship] = {}
        self.metrics_history: List[NetworkMetrics] = []
        self.current_metrics = NetworkMetrics()
        self.started_at = datetime.utcnow()
    
    def register_instance(self, instance_id: str, organization: str, region: str) -> bool:
        """Register a new OCX instance in the network"""
        if instance_id in self.instances:
            return False
        
        self.instances[instance_id] = {
            'instance_id': instance_id,
            'organization': organization,
            'region': region,
            'joined_at': datetime.utcnow(),
            'active': True,
            'total_relationships': 0,
            'total_interactions': 0,
        }
        
        # Update metrics
        self._update_metrics()
        
        print(f"📝 Registered OCX instance: {instance_id} ({organization}, {region})")
        print(f"   Network size: {self.current_metrics.active_instances} instances")
        print(f"   Network value: {self.current_metrics.network_value:.0f} relationships")
        
        return True
    
    def establish_relationship(self, instance1_id: str, instance2_id: str) -> Optional[OCXRelationship]:
        """Establish a relationship between two instances"""
        if instance1_id not in self.instances or instance2_id not in self.instances:
            raise ValueError("Both instances must be registered")
        
        # Check if relationship already exists
        relationship_key = self._get_relationship_key(instance1_id, instance2_id)
        if relationship_key in self.relationships:
            return self.relationships[relationship_key]
        
        # Create new relationship
        relationship = OCXRelationship(instance1_id, instance2_id)
        self.relationships[relationship_key] = relationship
        
        # Update instance relationship counts
        self.instances[instance1_id]['total_relationships'] += 1
        self.instances[instance2_id]['total_relationships'] += 1
        
        # Update metrics
        self._update_metrics()
        
        print(f"🤝 Established relationship: {instance1_id} ↔ {instance2_id}")
        
        return relationship
    
    def record_interaction(self, instance1_id: str, instance2_id: str, 
                          success: bool, trust_level: float, value_created: float = 0.0):
        """Record an interaction between two instances"""
        relationship_key = self._get_relationship_key(instance1_id, instance2_id)
        relationship = self.relationships.get(relationship_key)
        
        if not relationship:
            # Auto-establish relationship if it doesn't exist
            relationship = self.establish_relationship(instance1_id, instance2_id)
        
        # Record interaction
        relationship.record_interaction(success, trust_level, value_created)
        
        # Update instance interaction counts
        self.instances[instance1_id]['total_interactions'] += 1
        self.instances[instance2_id]['total_interactions'] += 1
        
        # Update metrics
        self._update_metrics()
    
    def _get_relationship_key(self, instance1_id: str, instance2_id: str) -> str:
        """Get a consistent key for a relationship (order-independent)"""
        return f"{min(instance1_id, instance2_id)}:{max(instance1_id, instance2_id)}"
    
    def _update_metrics(self):
        """Update network metrics"""
        # Count active instances
        active_instances = sum(1 for inst in self.instances.values() if inst['active'])
        
        # Calculate network value (Metcalfe's Law)
        network_value = active_instances * (active_instances - 1) / 2 if active_instances > 1 else 0
        
        # Count active relationships
        active_relationships = sum(1 for rel in self.relationships.values() if rel.active)
        
        # Calculate total interactions and value
        total_interactions = sum(rel.total_interactions for rel in self.relationships.values())
        total_value_created = sum(rel.total_value_created for rel in self.relationships.values())
        
        # Calculate average trust level
        trust_levels = [rel.avg_trust_level for rel in self.relationships.values() if rel.total_interactions > 0]
        avg_trust_level = sum(trust_levels) / len(trust_levels) if trust_levels else 0.0
        
        # Calculate growth rate
        if len(self.metrics_history) > 0:
            prev_metrics = self.metrics_history[-1]
            time_delta = (datetime.utcnow() - prev_metrics.timestamp).total_seconds() / 86400  # days
            if time_delta > 0:
                instance_growth = active_instances - prev_metrics.active_instances
                growth_rate = (instance_growth / time_delta) if prev_metrics.active_instances > 0 else 0
            else:
                growth_rate = 0
        else:
            growth_rate = 0
        
        # Determine current phase
        if active_instances < 20:
            current_phase = NetworkPhase.BILATERAL
        elif active_instances < 200:
            current_phase = NetworkPhase.INDUSTRY
        else:
            current_phase = NetworkPhase.GLOBAL
        
        # Update current metrics
        self.current_metrics.timestamp = datetime.utcnow()
        self.current_metrics.total_instances = len(self.instances)
        self.current_metrics.active_instances = active_instances
        self.current_metrics.total_relationships = len(self.relationships)
        self.current_metrics.active_relationships = active_relationships
        self.current_metrics.network_value = network_value
        self.current_metrics.total_interactions = total_interactions
        self.current_metrics.total_value_created = total_value_created
        self.current_metrics.avg_trust_level = avg_trust_level
        self.current_metrics.growth_rate = growth_rate
        self.current_metrics.current_phase = current_phase
    
    def take_snapshot(self):
        """Take a snapshot of current metrics"""
        # Create a copy of current metrics
        snapshot = NetworkMetrics()
        snapshot.timestamp = self.current_metrics.timestamp
        snapshot.total_instances = self.current_metrics.total_instances
        snapshot.active_instances = self.current_metrics.active_instances
        snapshot.total_relationships = self.current_metrics.total_relationships
        snapshot.active_relationships = self.current_metrics.active_relationships
        snapshot.network_value = self.current_metrics.network_value
        snapshot.total_interactions = self.current_metrics.total_interactions
        snapshot.total_value_created = self.current_metrics.total_value_created
        snapshot.avg_trust_level = self.current_metrics.avg_trust_level
        snapshot.growth_rate = self.current_metrics.growth_rate
        snapshot.current_phase = self.current_metrics.current_phase
        
        self.metrics_history.append(snapshot)
        
        # Keep only last 365 snapshots (daily for a year)
        if len(self.metrics_history) > 365:
            self.metrics_history = self.metrics_history[-365:]
    
    def get_network_dashboard(self) -> Dict:
        """Get comprehensive network dashboard data"""
        return {
            'current_metrics': self.current_metrics.to_dict(),
            'phase_progress': self._get_phase_progress(),
            'top_relationships': self._get_top_relationships(10),
            'regional_distribution': self._get_regional_distribution(),
            'growth_projection': self._project_growth(),
        }
    
    def _get_phase_progress(self) -> Dict:
        """Get progress towards next phase"""
        active = self.current_metrics.active_instances
        
        if active < 20:
            return {
                'current_phase': NetworkPhase.BILATERAL.value,
                'progress': active / 20,
                'next_phase': NetworkPhase.INDUSTRY.value,
                'instances_to_next_phase': 20 - active,
            }
        elif active < 200:
            return {
                'current_phase': NetworkPhase.INDUSTRY.value,
                'progress': (active - 20) / 180,
                'next_phase': NetworkPhase.GLOBAL.value,
                'instances_to_next_phase': 200 - active,
            }
        else:
            return {
                'current_phase': NetworkPhase.GLOBAL.value,
                'progress': 1.0,
                'next_phase': None,
                'instances_to_next_phase': 0,
            }
    
    def _get_top_relationships(self, limit: int) -> List[Dict]:
        """Get top relationships by interaction count"""
        sorted_relationships = sorted(
            self.relationships.values(),
            key=lambda r: r.total_interactions,
            reverse=True
        )
        
        return [rel.to_dict() for rel in sorted_relationships[:limit]]
    
    def _get_regional_distribution(self) -> Dict:
        """Get distribution of instances by region"""
        distribution = {}
        for inst in self.instances.values():
            if inst['active']:
                region = inst['region']
                distribution[region] = distribution.get(region, 0) + 1
        
        return distribution
    
    def _project_growth(self) -> Dict:
        """Project network growth for next 12 months"""
        if self.current_metrics.growth_rate <= 0:
            return {
                'projection_available': False,
                'reason': 'Insufficient growth data',
            }
        
        current_instances = self.current_metrics.active_instances
        daily_growth = self.current_metrics.growth_rate
        
        projections = []
        for months in [1, 3, 6, 12]:
            days = months * 30
            projected_instances = int(current_instances + (daily_growth * days))
            projected_network_value = projected_instances * (projected_instances - 1) / 2
            
            projections.append({
                'months': months,
                'projected_instances': projected_instances,
                'projected_relationships': int(projected_network_value),
                'growth_multiple': projected_instances / current_instances if current_instances > 0 else 0,
            })
        
        return {
            'projection_available': True,
            'daily_growth_rate': daily_growth,
            'projections': projections,
        }


# Example usage
if __name__ == "__main__":
    tracker = NetworkEffectsTracker()
    
    # Register instances
    instances = [
        ("ocx-us-west1-001", "Acme Corp", "us-west1"),
        ("ocx-us-east1-001", "TechCo", "us-east1"),
        ("ocx-eu-west1-001", "Global Finance", "eu-west1"),
        ("ocx-ap-south1-001", "Healthcare Systems", "ap-south1"),
        ("ocx-us-central1-001", "Manufacturing Alliance", "us-central1"),
    ]
    
    for instance_id, org, region in instances:
        tracker.register_instance(instance_id, org, region)
    
    # Establish relationships
    tracker.establish_relationship("ocx-us-west1-001", "ocx-us-east1-001")
    tracker.establish_relationship("ocx-us-west1-001", "ocx-eu-west1-001")
    tracker.establish_relationship("ocx-us-east1-001", "ocx-ap-south1-001")
    
    # Record interactions
    tracker.record_interaction("ocx-us-west1-001", "ocx-us-east1-001", 
                              success=True, trust_level=0.85, value_created=100.0)
    tracker.record_interaction("ocx-us-west1-001", "ocx-eu-west1-001", 
                              success=True, trust_level=0.92, value_created=150.0)
    
    # Get dashboard
    dashboard = tracker.get_network_dashboard()
    
    print("\n📊 Network Effects Dashboard:")
    print(f"   Phase: {dashboard['current_metrics']['current_phase']}")
    print(f"   Instances: {dashboard['current_metrics']['active_instances']}")
    print(f"   Relationships: {dashboard['current_metrics']['total_relationships']}")
    print(f"   Network Value: {dashboard['current_metrics']['network_value']:.0f}")
    print(f"   Avg Trust: {dashboard['current_metrics']['avg_trust_level']:.2f}")
    print(f"   Total Value Created: ${dashboard['current_metrics']['total_value_created']:.2f}")
