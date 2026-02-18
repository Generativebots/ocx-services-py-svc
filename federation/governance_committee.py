"""
OCX Standards Committee - Governance Structure for Inter-OCX Protocol

Manages protocol governance with 22 members across three categories:
- 10 Enterprise Representatives (2 votes each)
- 8 Technology Partners (1 vote each)
- 4 Academic/Research (1 vote each)

Total: 28 votes, requiring 75% supermajority (21 votes) for protocol changes.
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum
import logging
logger = logging.getLogger(__name__)



class MemberRole(Enum):
    """Member role in the standards committee"""
    ENTERPRISE = "Enterprise Representative"
    TECH_PARTNER = "Technology Partner"
    ACADEMIC = "Academic/Research"


class ProposalStatus(Enum):
    """Status of a governance proposal"""
    DRAFT = "DRAFT"
    VOTING = "VOTING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    IMPLEMENTED = "IMPLEMENTED"


class CommitteeMember:
    """Represents a member of the OCX Standards Committee"""
    
    def __init__(self, member_id: str, organization: str, role: MemberRole, votes: int) -> None:
        self.member_id = member_id
        self.organization = organization
        self.role = role
        self.votes = votes
        self.joined_at = datetime.utcnow()
        self.active = True
    
    def to_dict(self) -> Dict:
        return {
            'member_id': self.member_id,
            'organization': self.organization,
            'role': self.role.value,
            'votes': self.votes,
            'joined_at': self.joined_at.isoformat(),
            'active': self.active,
        }


class GovernanceProposal:
    """Represents a proposal for protocol changes"""
    
    def __init__(self, title: str, description: str, proposed_by: str, proposal_type: str) -> None:
        self.proposal_id = str(uuid.uuid4())
        self.title = title
        self.description = description
        self.proposed_by = proposed_by
        self.proposal_type = proposal_type  # "PROTOCOL_CHANGE", "VERSION_UPDATE", "STANDARD_ADDITION"
        self.status = ProposalStatus.DRAFT
        self.created_at = datetime.utcnow()
        self.voting_starts_at: Optional[datetime] = None
        self.voting_ends_at: Optional[datetime] = None
        self.votes_for: List[str] = []
        self.votes_against: List[str] = []
        self.vote_count_for = 0
        self.vote_count_against = 0
        self.implementation_notes = ""
    
    def to_dict(self) -> Dict:
        return {
            'proposal_id': self.proposal_id,
            'title': self.title,
            'description': self.description,
            'proposed_by': self.proposed_by,
            'proposal_type': self.proposal_type,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'voting_starts_at': self.voting_starts_at.isoformat() if self.voting_starts_at else None,
            'voting_ends_at': self.voting_ends_at.isoformat() if self.voting_ends_at else None,
            'votes_for': self.votes_for,
            'votes_against': self.votes_against,
            'vote_count_for': self.vote_count_for,
            'vote_count_against': self.vote_count_against,
            'implementation_notes': self.implementation_notes,
        }


class OCXStandardsCommittee:
    """
    OCX Standards Committee - Governance for the Inter-OCX Protocol
    
    Responsibilities:
    - Protocol version control
    - Standard approval/rejection
    - Backward compatibility guarantees
    - Dispute resolution
    """
    
    SUPERMAJORITY_THRESHOLD = 0.75  # 75% required for approval
    VOTING_PERIOD_DAYS = 14  # 2 weeks
    
    def __init__(self, tenant_id: str = None) -> None:
        self.members: Dict[str, CommitteeMember] = {}
        self.proposals: Dict[str, GovernanceProposal] = {}
        self.protocol_versions: List[str] = ["1.0"]
        self.current_version = "1.0"
        
        # Override from governance config if available
        if tenant_id:
            try:
                from config.governance_config import get_tenant_governance_config
                cfg = get_tenant_governance_config(tenant_id)
                self.SUPERMAJORITY_THRESHOLD = cfg.get("supermajority_threshold", 0.75)
                logger.info(f"Standards Committee configured from tenant governance: "
                           f"supermajority={self.SUPERMAJORITY_THRESHOLD}")
            except ImportError:
                pass
        
        # Initialize default committee members
        self._initialize_committee()
    
    def _initialize_committee(self) -> None:
        """Initialize the 22-member committee"""
        
        # 10 Enterprise Representatives (2 votes each)
        enterprises = [
            ("Acme Corp", "ENT-001"),
            ("TechCo Industries", "ENT-002"),
            ("Global Finance Inc", "ENT-003"),
            ("Healthcare Systems Ltd", "ENT-004"),
            ("Manufacturing Alliance", "ENT-005"),
            ("Retail Consortium", "ENT-006"),
            ("Energy Partners", "ENT-007"),
            ("Logistics Network", "ENT-008"),
            ("Insurance Group", "ENT-009"),
            ("Telecom United", "ENT-010"),
        ]
        
        for org, member_id in enterprises:
            self.add_member(member_id, org, MemberRole.ENTERPRISE, votes=2)
        
        # 8 Technology Partners (1 vote each)
        tech_partners = [
            ("Google Cloud", "TECH-001"),
            ("AWS", "TECH-002"),
            ("Microsoft Azure", "TECH-003"),
            ("IBM", "TECH-004"),
            ("Oracle", "TECH-005"),
            ("SAP", "TECH-006"),
            ("Salesforce", "TECH-007"),
            ("Red Hat", "TECH-008"),
        ]
        
        for org, member_id in tech_partners:
            self.add_member(member_id, org, MemberRole.TECH_PARTNER, votes=1)
        
        # 4 Academic/Research (1 vote each)
        academic = [
            ("MIT", "ACAD-001"),
            ("Stanford", "ACAD-002"),
            ("Carnegie Mellon", "ACAD-003"),
            ("Berkeley", "ACAD-004"),
        ]
        
        for org, member_id in academic:
            self.add_member(member_id, org, MemberRole.ACADEMIC, votes=1)
        
        print(f"✅ Initialized OCX Standards Committee with {len(self.members)} members")
    
    def add_member(self, member_id: str, organization: str, role: MemberRole, votes: int) -> Any:
        """Add a member to the committee"""
        member = CommitteeMember(member_id, organization, role, votes)
        self.members[member_id] = member
        return member
    
    def remove_member(self, member_id: str) -> None:
        """Remove a member from the committee"""
        if member_id in self.members:
            self.members[member_id].active = False
    
    def create_proposal(self, title: str, description: str, proposed_by: str, proposal_type: str) -> GovernanceProposal:
        """Create a new governance proposal"""
        
        # Verify proposer is a committee member
        if proposed_by not in self.members:
            raise ValueError(f"Proposer {proposed_by} is not a committee member")
        
        proposal = GovernanceProposal(title, description, proposed_by, proposal_type)
        self.proposals[proposal.proposal_id] = proposal
        
        print(f"📝 Created proposal: {title} (ID: {proposal.proposal_id})")
        
        return proposal
    
    def start_voting(self, proposal_id: str) -> bool:
        """Start voting period for a proposal"""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        if proposal.status != ProposalStatus.DRAFT:
            raise ValueError(f"Proposal must be in DRAFT status to start voting")
        
        proposal.status = ProposalStatus.VOTING
        proposal.voting_starts_at = datetime.utcnow()
        proposal.voting_ends_at = datetime.utcnow() + timedelta(days=self.VOTING_PERIOD_DAYS)
        
        print(f"🗳️  Voting started for: {proposal.title}")
        print(f"   Voting ends: {proposal.voting_ends_at.isoformat()}")
        
        return True
    
    def cast_vote(self, proposal_id: str, member_id: str, vote_for: bool) -> bool:
        """Cast a vote on a proposal"""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        if proposal.status != ProposalStatus.VOTING:
            raise ValueError(f"Proposal is not in voting status")
        
        if datetime.utcnow() > proposal.voting_ends_at:
            raise ValueError(f"Voting period has ended")
        
        member = self.members.get(member_id)
        if not member or not member.active:
            raise ValueError(f"Member {member_id} not found or inactive")
        
        # Remove previous vote if exists
        if member_id in proposal.votes_for:
            proposal.votes_for.remove(member_id)
            proposal.vote_count_for -= member.votes
        if member_id in proposal.votes_against:
            proposal.votes_against.remove(member_id)
            proposal.vote_count_against -= member.votes
        
        # Record new vote
        if vote_for:
            proposal.votes_for.append(member_id)
            proposal.vote_count_for += member.votes
        else:
            proposal.votes_against.append(member_id)
            proposal.vote_count_against += member.votes
        
        print(f"✅ Vote recorded: {member.organization} voted {'FOR' if vote_for else 'AGAINST'} ({member.votes} votes)")
        
        return True
    
    def finalize_voting(self, proposal_id: str) -> bool:
        """Finalize voting and determine outcome"""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        if proposal.status != ProposalStatus.VOTING:
            raise ValueError(f"Proposal is not in voting status")
        
        # Calculate total possible votes
        total_votes = sum(m.votes for m in self.members.values() if m.active)
        
        # Calculate approval percentage
        approval_rate = proposal.vote_count_for / total_votes if total_votes > 0 else 0
        
        # Determine outcome
        if approval_rate >= self.SUPERMAJORITY_THRESHOLD:
            proposal.status = ProposalStatus.APPROVED
            print(f"✅ Proposal APPROVED: {proposal.title}")
            print(f"   Votes: {proposal.vote_count_for}/{total_votes} ({approval_rate*100:.1f}%)")
        else:
            proposal.status = ProposalStatus.REJECTED
            print(f"❌ Proposal REJECTED: {proposal.title}")
            print(f"   Votes: {proposal.vote_count_for}/{total_votes} ({approval_rate*100:.1f}%)")
            print(f"   Required: {self.SUPERMAJORITY_THRESHOLD*100:.1f}%")
        
        return proposal.status == ProposalStatus.APPROVED
    
    def implement_proposal(self, proposal_id: str, implementation_notes: str) -> bool:
        """Mark a proposal as implemented"""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError(f"Only approved proposals can be implemented")
        
        proposal.status = ProposalStatus.IMPLEMENTED
        proposal.implementation_notes = implementation_notes
        
        print(f"🚀 Proposal implemented: {proposal.title}")
        
        return True
    
    def add_protocol_version(self, version: str, approved_proposal_id: str) -> bool:
        """Add a new protocol version"""
        proposal = self.proposals.get(approved_proposal_id)
        if not proposal or proposal.status != ProposalStatus.APPROVED:
            raise ValueError(f"Proposal must be approved to add protocol version")
        
        self.protocol_versions.append(version)
        self.current_version = version
        
        print(f"📋 Added protocol version: {version}")
        
        return True
    
    def get_voting_statistics(self) -> Dict:
        """Get voting statistics"""
        total_proposals = len(self.proposals)
        approved = sum(1 for p in self.proposals.values() if p.status == ProposalStatus.APPROVED)
        rejected = sum(1 for p in self.proposals.values() if p.status == ProposalStatus.REJECTED)
        voting = sum(1 for p in self.proposals.values() if p.status == ProposalStatus.VOTING)
        implemented = sum(1 for p in self.proposals.values() if p.status == ProposalStatus.IMPLEMENTED)
        
        return {
            'total_proposals': total_proposals,
            'approved': approved,
            'rejected': rejected,
            'voting': voting,
            'implemented': implemented,
            'approval_rate': approved / total_proposals if total_proposals > 0 else 0,
            'total_members': len([m for m in self.members.values() if m.active]),
            'total_votes': sum(m.votes for m in self.members.values() if m.active),
            'protocol_versions': self.protocol_versions,
            'current_version': self.current_version,
        }
    
    def get_member_voting_record(self, member_id: str) -> Dict:
        """Get voting record for a member"""
        member = self.members.get(member_id)
        if not member:
            raise ValueError(f"Member {member_id} not found")
        
        votes_cast = 0
        votes_for = 0
        votes_against = 0
        
        for proposal in self.proposals.values():
            if member_id in proposal.votes_for:
                votes_cast += 1
                votes_for += 1
            elif member_id in proposal.votes_against:
                votes_cast += 1
                votes_against += 1
        
        return {
            'member_id': member_id,
            'organization': member.organization,
            'role': member.role.value,
            'votes_per_proposal': member.votes,
            'total_proposals_voted': votes_cast,
            'votes_for': votes_for,
            'votes_against': votes_against,
            'participation_rate': votes_cast / len(self.proposals) if len(self.proposals) > 0 else 0,
        }


# Example usage
if __name__ == "__main__":
    committee = OCXStandardsCommittee()
    
    # Create a proposal
    proposal = committee.create_proposal(
        title="Add Multi-Region Support to Handshake Protocol",
        description="Extend the 6-step handshake to support multi-region trust attestation",
        proposed_by="ENT-001",
        proposal_type="PROTOCOL_CHANGE"
    )
    
    # Start voting
    committee.start_voting(proposal.proposal_id)
    
    # Cast votes (simulating committee voting)
    # Enterprise votes (2 votes each)
    for i in range(1, 11):
        member_id = f"ENT-{i:03d}"
        committee.cast_vote(proposal.proposal_id, member_id, vote_for=True)
    
    # Tech partner votes (1 vote each)
    for i in range(1, 9):
        member_id = f"TECH-{i:03d}"
        committee.cast_vote(proposal.proposal_id, member_id, vote_for=True)
    
    # Academic votes (1 vote each)
    for i in range(1, 5):
        member_id = f"ACAD-{i:03d}"
        committee.cast_vote(proposal.proposal_id, member_id, vote_for=True)
    
    # Finalize voting
    committee.finalize_voting(proposal.proposal_id)
    
    # Get statistics
    stats = committee.get_voting_statistics()
    print(f"\n📊 Governance Statistics:")
    print(f"   Total Proposals: {stats['total_proposals']}")
    print(f"   Approved: {stats['approved']}")
    print(f"   Approval Rate: {stats['approval_rate']*100:.1f}%")
    print(f"   Total Members: {stats['total_members']}")
    print(f"   Total Votes: {stats['total_votes']}")
