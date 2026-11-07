package s3m.roe

# Unit tests for Charlie-3 ROE policy used in tactical positive-ID gating.

test_allow_military_with_positive_id {
    allow with input as {
        "target_type": "military",
        "positive_id": true,
    }
}

test_deny_without_positive_id {
    not allow with input as {
        "target_type": "military",
        "positive_id": false,
    }
}
