package cortex.authz_test

import data.cortex.authz

test_allow_brokered_change {
    authz.allow with input as {
        "via_broker": true,
        "policy_gate_allowed": true,
        "tainted_instruction": false,
        "forbidden_tool": false,
    }
}

test_deny_without_broker {
    not authz.allow with input as {
        "via_broker": false,
        "policy_gate_allowed": true,
        "tainted_instruction": false,
        "forbidden_tool": false,
    }
}

test_deny_when_gate_denies {
    not authz.allow with input as {
        "via_broker": true,
        "policy_gate_allowed": false,
        "tainted_instruction": false,
        "forbidden_tool": false,
    }
}

test_deny_tainted_instruction {
    not authz.allow with input as {
        "via_broker": true,
        "policy_gate_allowed": true,
        "tainted_instruction": true,
        "forbidden_tool": false,
    }
}

test_deny_forbidden_tool {
    not authz.allow with input as {
        "via_broker": true,
        "policy_gate_allowed": true,
        "tainted_instruction": false,
        "forbidden_tool": true,
    }
}

test_core_tier_under_sovereign_profile {
    authz.tier_allows_core with input as {
        "tier": "core",
        "deployment_profile": "government_sovereign",
    }
}

test_edge_tier_requires_offline {
    authz.tier_requires_offline with input as {
        "tier": "edge",
        "offline_required": true,
    }
}

test_deny_reason_broker_bypass {
    authz.deny_reason == "direct change bypassed broker" with input as {
        "via_broker": false,
    }
}
