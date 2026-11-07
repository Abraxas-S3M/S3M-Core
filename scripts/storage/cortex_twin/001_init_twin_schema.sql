-- Cortex bitemporal twin graph store (nodes + edges).
-- Military/tactical context: partition-scoped operational topology with full
-- audit history for reachability "time machine" queries after incidents.

CREATE TABLE IF NOT EXISTS cortex_twin_nodes (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    partition_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL,
    source_name TEXT NOT NULL,
    source_trust TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cortex_twin_nodes_partition_entity
    ON cortex_twin_nodes (tenant_id, partition_id, entity_id);

CREATE INDEX IF NOT EXISTS idx_cortex_twin_nodes_validity
    ON cortex_twin_nodes (tenant_id, partition_id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS cortex_twin_edges (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    partition_id TEXT NOT NULL,
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    traversal_probability DOUBLE PRECISION,
    required BOOLEAN NOT NULL DEFAULT FALSE,
    xiid_resource_id TEXT,
    is_boundary BOOLEAN NOT NULL DEFAULT FALSE,
    boundary_peer_partition_id TEXT,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL,
    source_name TEXT NOT NULL,
    source_trust TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cortex_twin_edges_partition_endpoints
    ON cortex_twin_edges (tenant_id, partition_id, source_entity_id, target_entity_id);

CREATE INDEX IF NOT EXISTS idx_cortex_twin_edges_validity
    ON cortex_twin_edges (tenant_id, partition_id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS cortex_twin_partition_links (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    source_partition_id TEXT NOT NULL,
    target_partition_id TEXT NOT NULL,
    link_kind TEXT NOT NULL DEFAULT 'boundary',
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL,
    source_name TEXT NOT NULL,
    source_trust TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cortex_twin_partition_links_validity
    ON cortex_twin_partition_links (tenant_id, source_partition_id, valid_from, valid_to);
