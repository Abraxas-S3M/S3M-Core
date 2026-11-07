package s3m.cortex.authority_test

import rego.v1

import data.s3m.cortex.authority

test_final_allow_happy_path if {
    authority.final_allow with input as {
        "python": {"allow": true},
        "actor": {"id": "op-7", "grants": ["isolate_host", "rotate_cred"]},
        "parent": {"grants": ["isolate_host", "rotate_cred", "quarantine_net"]},
        "approval": {"operator_id": "op-7", "duress": false},
        "requested_action": "isolate_host",
        "change_id": "CHG-42",
        "required_approvals": 2,
        "approvals_for_change": 2,
    }
}

test_deny_when_child_exceeds_parent_envelope if {
    not authority.final_allow with input as {
        "python": {"allow": true},
        "actor": {"id": "op-7", "grants": ["quarantine_net"]},
        "parent": {"grants": ["isolate_host"]},
        "approval": {"operator_id": "op-7", "duress": false},
        "requested_action": "quarantine_net",
        "change_id": "CHG-43",
        "required_approvals": 1,
        "approvals_for_change": 1,
    }
}

test_duress_does_not_count_toward_quorum if {
    not authority.final_allow with input as {
        "python": {"allow": true},
        "actor": {"id": "op-9", "grants": ["isolate_host"]},
        "parent": {"grants": ["isolate_host"]},
        "approval": {"operator_id": "op-9", "duress": true},
        "requested_action": "isolate_host",
        "change_id": "CHG-44",
        "required_approvals": 2,
        "approvals_for_change": 1,
    }
}

test_deny_when_python_engine_denies if {
    not authority.final_allow with input as {
        "python": {"allow": false},
        "actor": {"id": "op-7", "grants": ["isolate_host"]},
        "parent": {"grants": ["isolate_host"]},
        "approval": {"operator_id": "op-7", "duress": false},
        "requested_action": "isolate_host",
        "change_id": "CHG-45",
        "required_approvals": 1,
        "approvals_for_change": 1,
    }
}
