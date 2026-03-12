"""Tests for federation service modules"""
import pytest
from unittest.mock import patch, MagicMock

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from governance_committee import (
    MemberRole, ProposalStatus, CommitteeMember, OCXStandardsCommittee,
)
from network_effects import NetworkPhase, OCXRelationship, NetworkEffectsTracker
from weighted_trust_calculator import WeightedTrustCalculator


class TestMemberRole:
    def test_enterprise_value(self):
        assert MemberRole.ENTERPRISE.value == "Enterprise Representative"
    def test_tech_partner_value(self):
        assert MemberRole.TECH_PARTNER.value == "Technology Partner"
    def test_academic_value(self):
        assert MemberRole.ACADEMIC.value == "Academic/Research"


class TestProposalStatus:
    def test_all_statuses(self):
        assert ProposalStatus.DRAFT.value == "DRAFT"
        assert ProposalStatus.VOTING.value == "VOTING"
        assert ProposalStatus.APPROVED.value == "APPROVED"
        assert ProposalStatus.REJECTED.value == "REJECTED"
        assert ProposalStatus.IMPLEMENTED.value == "IMPLEMENTED"


class TestCommitteeMember:
    def test_creation(self):
        m = CommitteeMember("m1", "Acme Corp", MemberRole.ENTERPRISE, 2)
        assert m.member_id == "m1"
        assert m.votes == 2
        assert m.active is True

    def test_to_dict(self):
        m = CommitteeMember("m1", "Acme Corp", MemberRole.ENTERPRISE, 2)
        d = m.to_dict()
        assert d["member_id"] == "m1"
        assert d["organization"] == "Acme Corp"


class TestOCXStandardsCommittee:
    def test_init_has_members(self):
        c = OCXStandardsCommittee()
        assert len(c.members) == 22  # initialized with 22 default members

    def test_add_member_by_args(self):
        c = OCXStandardsCommittee()
        m = c.add_member("new-1", "Acme", MemberRole.ENTERPRISE, 2)
        assert m.member_id == "new-1"
        assert "new-1" in c.members

    def test_create_proposal(self):
        c = OCXStandardsCommittee()
        # Use a member that exists from initialization
        member_id = list(c.members.keys())[0]
        proposal = c.create_proposal("Test Proposal", "Description", member_id, "STANDARD")
        assert proposal is not None
        assert proposal.title == "Test Proposal"


class TestNetworkPhase:
    def test_bilateral(self):
        assert NetworkPhase.BILATERAL.value == "Bilateral Partnerships"
    def test_industry(self):
        assert NetworkPhase.INDUSTRY.value == "Industry Adoption"
    def test_global(self):
        assert NetworkPhase.GLOBAL.value == "Global Network"


class TestOCXRelationship:
    def test_creation(self):
        r = OCXRelationship("ocx1", "ocx2")
        assert r.instance1_id == "ocx1"
        assert r.instance2_id == "ocx2"
        assert r.total_interactions == 0


class TestNetworkEffectsTracker:
    def test_init(self):
        t = NetworkEffectsTracker()
        assert hasattr(t, "relationships")


class TestWeightedTrustCalculator:
    def test_init(self):
        calc = WeightedTrustCalculator()
        assert calc is not None

    def test_calculate_trust(self):
        calc = WeightedTrustCalculator()
        result = calc.calculate_trust(
            audit_score=0.9,
            reputation_score=0.8,
            attestation_score=0.7,
            history_score=0.6,
        )
        assert isinstance(result, dict)
        assert "trust_level" in result

    def test_calculate_trust_all_ones(self):
        calc = WeightedTrustCalculator()
        result = calc.calculate_trust(1.0, 1.0, 1.0, 1.0)
        assert result["trust_level"] >= 0.9

    def test_calculate_trust_all_zeros(self):
        calc = WeightedTrustCalculator()
        result = calc.calculate_trust(0.0, 0.0, 0.0, 0.0)
        assert result["trust_level"] <= 0.1

    def test_calculate_trust_tax(self):
        calc = WeightedTrustCalculator()
        tax = calc.calculate_trust_tax(trust_level=0.5)
        assert isinstance(tax, float)
        assert tax > 0
