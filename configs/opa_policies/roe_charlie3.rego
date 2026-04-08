package s3m.roe

default allow = false

allow {
    input.target_type == "military"
    input.positive_id == true
}

deny_reason = "Positive ID required near civilian zones" {
    not input.positive_id
}
