---- MODULE ROE ----
(*
  S3M Formal ROE Specification - Gap 7 of 7
  TLA+ model for Rules of Engagement enforcement.

  Core invariants:
    1. No lethal effect without explicit human approval.
    2. Approval cannot be granted by the requesting subsystem itself.
    3. Every lethal action is preceded by an immutable audit entry.

  Verify with: tlc -config ROE.cfg ROE.tla
*)

EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
  Subsystems,         \* e.g. {"autonomy", "threat_detection"}
  HumanOperators,     \* e.g. {"commander", "operator"}
  MaxActions          \* bound for model checking

VARIABLES
  pending_approvals,  \* set of [action, requestor, ticket_id]
  granted_approvals,  \* set of [ticket_id, operator]
  audit_log,          \* append-only sequence of records
  lethal_actions_taken

vars == <<pending_approvals, granted_approvals, audit_log, lethal_actions_taken>>

\* -- Type Invariant ----------------------------------------------------------
TypeInvariant ==
  /\ pending_approvals \subseteq
       [action: {"LETHAL_ENGAGE"}, requestor: Subsystems, ticket_id: 1..MaxActions]
  /\ granted_approvals \subseteq
       [ticket_id: 1..MaxActions, operator: HumanOperators]
  /\ audit_log \in Seq([type: STRING, ticket: Nat, actor: STRING])
  /\ lethal_actions_taken \in Nat

\* -- Safety Invariants -------------------------------------------------------
NoLethalWithoutApproval ==
  \A i \in 1..Len(audit_log) :
    audit_log[i].type = "LETHAL_EXECUTED" =>
      \E j \in 1..(i - 1) :
        /\ audit_log[j].type = "APPROVAL_GRANTED"
        /\ audit_log[j].ticket = audit_log[i].ticket

SelfApprovalForbidden ==
  /\ HumanOperators \cap Subsystems = {}
  /\ \A g \in granted_approvals :
      \E p \in pending_approvals :
        /\ p.ticket_id = g.ticket_id
        /\ g.operator # p.requestor

AuditPrecedesLethal ==
  lethal_actions_taken > 0 => Len(audit_log) > 0

\* -- Initial State -----------------------------------------------------------
Init ==
  /\ pending_approvals = {}
  /\ granted_approvals = {}
  /\ audit_log = << >>
  /\ lethal_actions_taken = 0

\* -- Actions -----------------------------------------------------------------
RequestApproval(subsys, ticket_id) ==
  /\ subsys \in Subsystems
  /\ ticket_id \in 1..MaxActions
  /\ ~\E t \in pending_approvals : t.ticket_id = ticket_id
  /\ pending_approvals' = pending_approvals \union
       {[action |-> "LETHAL_ENGAGE", requestor |-> subsys, ticket_id |-> ticket_id]}
  /\ audit_log' = Append(
       audit_log,
       [type |-> "APPROVAL_REQUESTED", ticket |-> ticket_id, actor |-> subsys]
     )
  /\ UNCHANGED <<granted_approvals, lethal_actions_taken>>

GrantApproval(operator, ticket_id) ==
  /\ operator \in HumanOperators
  /\ ticket_id \in 1..MaxActions
  /\ \E t \in pending_approvals : t.ticket_id = ticket_id
  /\ ~\E g \in granted_approvals : g.ticket_id = ticket_id
  /\ granted_approvals' = granted_approvals \union
       {[ticket_id |-> ticket_id, operator |-> operator]}
  /\ audit_log' = Append(
       audit_log,
       [type |-> "APPROVAL_GRANTED", ticket |-> ticket_id, actor |-> operator]
     )
  /\ UNCHANGED <<pending_approvals, lethal_actions_taken>>

ExecuteLethalAction(ticket_id) ==
  /\ ticket_id \in 1..MaxActions
  /\ \E g \in granted_approvals : g.ticket_id = ticket_id
  /\ lethal_actions_taken < MaxActions
  /\ lethal_actions_taken' = lethal_actions_taken + 1
  /\ audit_log' = Append(
       audit_log,
       [type |-> "LETHAL_EXECUTED", ticket |-> ticket_id, actor |-> "system"]
     )
  /\ UNCHANGED <<pending_approvals, granted_approvals>>

\* -- Next --------------------------------------------------------------------
Next ==
  \/ \E s \in Subsystems, t \in 1..MaxActions : RequestApproval(s, t)
  \/ \E o \in HumanOperators, t \in 1..MaxActions : GrantApproval(o, t)
  \/ \E t \in 1..MaxActions : ExecuteLethalAction(t)

\* -- Spec --------------------------------------------------------------------
Spec == Init /\ [][Next]_vars

\* -- Properties to Verify ----------------------------------------------------
THEOREM Spec => [](TypeInvariant /\ NoLethalWithoutApproval /\ SelfApprovalForbidden /\ AuditPrecedesLethal)

====
