"""
S3M advanced negotiation protocols for tactical swarm coordination.

This package extends baseline task allocation with FIPA Contract Net behavior
for mission bidding in contested military environments.
"""

from .contract_net import (
    CallForProposal,
    ContractNetProtocol,
    NegotiationResult,
    NegotiationRound,
    Proposal,
    ProposalStatus,
)

__all__ = [
    "ContractNetProtocol",
    "CallForProposal",
    "Proposal",
    "ProposalStatus",
    "NegotiationRound",
    "NegotiationResult",
]
