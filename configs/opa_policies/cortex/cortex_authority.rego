# Cortex cyber write-authority policy (second independent engine).
# Military/tactical context: contested cyber ops require dual-engine consensus
# before defensive reconfiguration reaches live mission systems.
package s3m.cortex.authority

import rego.v1

default final_allow := false

attenuation_ok if {
    every grant in input.actor.grants {
        grant in input.parent.grants
    }
}

python_allow if {
    input.python.allow
}

operator_ok if {
    input.actor.id != ""
    input.actor.id == input.approval.operator_id
    input.approval.duress == false
}

scope_ok if {
    input.requested_action in input.actor.grants
}

change_quorum_ok if {
    input.change_id != ""
    input.approvals_for_change >= input.required_approvals
}

duress_excluded_from_quorum if {
    input.approval.duress == false
}

duress_excluded_from_quorum if {
    input.approval.duress
    input.approvals_for_change >= input.required_approvals
}

final_allow if {
    python_allow
    operator_ok
    scope_ok
    attenuation_ok
    change_quorum_ok
    duress_excluded_from_quorum
}
