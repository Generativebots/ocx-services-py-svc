"""
Activity Registry Test Script
Tests all major functionality
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8002"

def test_create_activity() -> None:
    """Test creating a new activity"""
    print("\n=== Test 1: Create Activity ===")
    
    response = requests.post(
        f"{BASE_URL}/api/v1/activities",
        json={
            "name": "PO_Approval",
            "version": "1.0.0",
            "ebcl_source": """ACTIVITY "PO_Approval"

OWNER Finance
VERSION 1.0
AUTHORITY "Procurement Policy v3.2"

TRIGGER
    ON Event.PurchaseRequest.Created

VALIDATE
    REQUIRE amount > 0
    REQUIRE vendor.isApproved == true

DECIDE
    IF amount <= 50000
        OUTCOME AutoApprove
    ELSE
        OUTCOME ManagerApproval

ACT
    AutoApprove:
        SYSTEM ERP.CREATE_PO
    ManagerApproval:
        HUMAN Manager.APPROVE
        SYSTEM WAIT Approval
        SYSTEM ERP.CREATE_PO

EVIDENCE
    LOG decision
    LOG policy_reference
    STORE immutable""",
            "owner": "Finance Department",
            "authority": "Procurement Policy v3.2",
            "created_by": "admin@company.com",
            "description": "Purchase order approval workflow",
            "category": "Procurement"
        }
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Activity ID: {data['activity_id']}")
        print(f"Status: {data['status']}")
        return data['activity_id']
    else:
        print(f"Error: {response.text}")
        return None

def test_request_approval(activity_id) -> Any:
    """Test requesting approval"""
    print("\n=== Test 2: Request Approval ===")
    
    response = requests.post(
        f"{BASE_URL}/api/v1/activities/{activity_id}/request-approval",
        json={
            "approver_id": "compliance@company.com",
            "approver_role": "Compliance Officer",
            "approval_type": "COMPLIANCE",
            "comments": "Please review for SOX compliance"
        }
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Approval ID: {data['approval_id']}")
        return data['approval_id']
    else:
        print(f"Error: {response.text}")
        return None

def test_approve_activity(activity_id, approval_id) -> None:
    """Test approving an activity"""
    print("\n=== Test 3: Approve Activity ===")
    
    response = requests.post(
        f"{BASE_URL}/api/v1/activities/{activity_id}/approve?approval_id={approval_id}",
        json={
            "approval_status": "APPROVED",
            "comments": "SOX compliant. Approved."
        }
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("Activity approved!")
    else:
        print(f"Error: {response.text}")

def test_deploy_activity(activity_id) -> Any:
    """Test deploying an activity"""
    print("\n=== Test 4: Deploy Activity ===")
    
    response = requests.post(
        f"{BASE_URL}/api/v1/activities/{activity_id}/deploy",
        json={
            "environment": "DEV",
            "tenant_id": "acme-corp",
            "deployed_by": "devops@company.com",
            "deployment_notes": "Initial DEV deployment"
        }
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Deployment ID: {data['deployment_id']}")
        print(f"Environment: {data['environment']}")
        return data['deployment_id']
    else:
        print(f"Error: {response.text}")
        return None

def test_get_latest_version() -> None:
    """Test getting latest version"""
    print("\n=== Test 5: Get Latest Version ===")
    
    response = requests.get(f"{BASE_URL}/api/v1/activities/latest/PO_Approval")
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Activity: {data['name']} v{data['version']}")
        print(f"Status: {data['status']}")
    else:
        print(f"Error: {response.text}")

def test_create_new_version(activity_id) -> Any:
    """Test creating a new version"""
    print("\n=== Test 6: Create New Version ===")
    
    response = requests.post(
        f"{BASE_URL}/api/v1/activities/{activity_id}/new-version",
        json={
            "version_type": "MINOR",
            "change_summary": "Added CFO approval for amounts > $50K",
            "breaking_changes": ["Changed approval threshold"],
            "created_by": "policy@company.com"
        }
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"New Version: {data['new_version']}")
        print(f"Previous Version: {data['previous_version']}")
        return data['new_activity_id']
    else:
        print(f"Error: {response.text}")
        return None

def test_list_activities() -> None:
    """Test listing activities"""
    print("\n=== Test 7: List Activities ===")
    
    response = requests.get(f"{BASE_URL}/api/v1/activities?category=Procurement")
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Found {len(data)} activities")
        for activity in data:
            print(f"  - {activity['name']} v{activity['version']} ({activity['status']})")
    else:
        print(f"Error: {response.text}")

def test_rollback(activity_id, deployment_id) -> None:
    """Test rollback"""
    print("\n=== Test 8: Rollback Deployment ===")
    
    response = requests.post(
        f"{BASE_URL}/api/v1/activities/{activity_id}/rollback?deployment_id={deployment_id}",
        json={
            "rollback_reason": "Testing rollback functionality",
            "rolled_back_by": "devops@company.com"
        }
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Rollback Status: {data['status']}")
    else:
        print(f"Error: {response.text}")

def test_health() -> None:
    """Test health check"""
    print("\n=== Test 0: Health Check ===")
    
    response = requests.get(f"{BASE_URL}/health")
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Service: {response.json()}")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    print("Activity Registry Test Suite")
    print("=" * 50)
    
    # Health check
    test_health()
    
    # Create activity
    activity_id = test_create_activity()
    
    if activity_id:
        # Request approval
        approval_id = test_request_approval(activity_id)
        
        if approval_id:
            # Approve
            test_approve_activity(activity_id, approval_id)
            
            # Deploy
            deployment_id = test_deploy_activity(activity_id)
            
            # Get latest version
            test_get_latest_version()
            
            # Create new version
            new_activity_id = test_create_new_version(activity_id)
            
            # List activities
            test_list_activities()
            
            # Rollback (if deployed)
            if deployment_id:
                test_rollback(activity_id, deployment_id)
    
    print("\n" + "=" * 50)
    print("Test suite complete!")
