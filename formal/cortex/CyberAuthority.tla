---- MODULE CyberAuthority ----
(*
  S3M Cortex cyber write-authority formal model.

  Covers:
    - envelope attenuation (child grants subset of parent grants)
    - rollback liveness (every executed change is verified or rolled back)
    - duress (duress approvals never satisfy Need(change))

  Verify with: tlc -config CyberAuthority.cfg CyberAuthority.tla
*)

EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
  Actors,
  Actions,
  Changes,
  MaxPending,
  ParentActor,
  ParentActorGrants,
  ChildActorGrants

VARIABLES
  parentGrants,    \* actor -> subset Actions
  childGrants,     \* actor -> subset Actions
  need,            \* change -> Nat quorum still required
  regularApprovals,\* change -> count of non-duress approvals
  executed,        \* set of executed changes
  verified,        \* set of verified changes
  rolledBack,      \* set of rolled back changes
  duressApprovals  \* set of changes approved under duress (audit only)

vars == <<parentGrants, childGrants, need, regularApprovals, executed, verified, rolledBack, duressApprovals>>

CONSTANT InitialNeed

\* ---------------------------------------------------------------------------
TypeOK ==
  /\ parentGrants \in [Actors -> SUBSET Actions]
  /\ childGrants \in [Actors -> SUBSET Actions]
  /\ need \in [Changes -> Nat]
  /\ regularApprovals \in [Changes -> Nat]
  /\ executed \subseteq Changes
  /\ verified \subseteq Changes
  /\ rolledBack \subseteq Changes
  /\ duressApprovals \subseteq Changes
  /\ verified \subseteq executed
  /\ rolledBack \subseteq executed
  /\ verified \cap rolledBack = {}

\* Envelope attenuation: delegated grants cannot exceed parent envelope.
EnvelopeAttenuation ==
  \A a \in Actors :
    childGrants[a] \subseteq parentGrants[a]

\* Duress approvals never decrease Need(c); only regular approvals do.
NoDuressQuorumImpact ==
  \A c \in Changes :
    need[c] = InitialNeed - regularApprovals[c]

\* Safety: a change cannot be both verified and rolled back.
ExclusiveOutcome ==
  verified \cap rolledBack = {}

\* Safety: verified/rolled-back changes must have been executed first.
OutcomeRequiresExecution ==
  /\ verified \subseteq executed
  /\ rolledBack \subseteq executed

Init ==
  /\ parentGrants = [a \in Actors |-> IF a = ParentActor THEN ParentActorGrants ELSE ChildActorGrants]
  /\ childGrants = [a \in Actors |-> {}]
  /\ need = [c \in Changes |-> InitialNeed]
  /\ regularApprovals = [c \in Changes |-> 0]
  /\ executed = {}
  /\ verified = {}
  /\ rolledBack = {}
  /\ duressApprovals = {}

DelegateGrant(actor, action) ==
  /\ actor \in Actors
  /\ action \in Actions
  /\ action \in parentGrants[actor]
  /\ childGrants' = [childGrants EXCEPT ![actor] = @ \union {action}]
  /\ UNCHANGED <<parentGrants, need, regularApprovals, executed, verified, rolledBack, duressApprovals>>

ApproveChange(change) ==
  /\ change \in Changes
  /\ need[change] > 0
  /\ need' = [need EXCEPT ![change] = need[change] - 1]
  /\ regularApprovals' = [regularApprovals EXCEPT ![change] = regularApprovals[change] + 1]
  /\ UNCHANGED <<parentGrants, childGrants, executed, verified, rolledBack, duressApprovals>>

DuressApprove(change) ==
  /\ change \in Changes
  /\ need[change] > 0
  /\ duressApprovals' = duressApprovals \union {change}
  /\ UNCHANGED <<parentGrants, childGrants, need, regularApprovals, executed, verified, rolledBack>>

ExecuteChange(change) ==
  /\ change \in Changes
  /\ need[change] = 0
  /\ change \notin executed
  /\ executed' = executed \union {change}
  /\ UNCHANGED <<parentGrants, childGrants, need, regularApprovals, verified, rolledBack, duressApprovals>>

VerifyChange(change) ==
  /\ change \in executed
  /\ change \notin verified
  /\ change \notin rolledBack
  /\ verified' = verified \union {change}
  /\ UNCHANGED <<parentGrants, childGrants, need, regularApprovals, executed, rolledBack, duressApprovals>>

RollbackChange(change) ==
  /\ change \in executed
  /\ change \notin verified
  /\ change \notin rolledBack
  /\ rolledBack' = rolledBack \union {change}
  /\ UNCHANGED <<parentGrants, childGrants, need, regularApprovals, executed, verified, duressApprovals>>

Next ==
  \/ \E a \in Actors, act \in Actions : DelegateGrant(a, act)
  \/ \E c \in Changes : ApproveChange(c)
  \/ \E c \in Changes : DuressApprove(c)
  \/ \E c \in Changes : ExecuteChange(c)
  \/ \E c \in Changes : VerifyChange(c)
  \/ \E c \in Changes : RollbackChange(c)

Fairness ==
  /\ \A c \in Changes : WF_vars(ApproveChange(c))
  /\ \A c \in Changes : WF_vars(VerifyChange(c))
  /\ \A c \in Changes : WF_vars(RollbackChange(c))

Spec == Init /\ [][Next]_vars /\ Fairness

LivenessVerifiedOrRolledBack ==
  \A c \in Changes :
    c \in executed => <>((c \in verified) \/ (c \in rolledBack))

====
