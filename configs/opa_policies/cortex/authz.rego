package cortex.authz

default allow = false

allow {
    input.via_broker == true
    input.policy_gate_allowed == true
    not input.tainted_instruction
    not input.forbidden_tool
}

deny_reason = "direct change bypassed broker" {
    not input.via_broker
}

deny_reason = "policy gate denied action" {
    input.via_broker
    not input.policy_gate_allowed
}

deny_reason = "untrusted channel carried instruction markers" {
    input.tainted_instruction
}

deny_reason = "tool forbidden for Cortex agents" {
    input.forbidden_tool
}

tier_allows_core {
    input.tier == "core"
    input.deployment_profile == "government_sovereign"
}

tier_requires_offline {
    input.tier == "edge"
    input.offline_required == true
}
