"""Additive P3 schema. Applied migration SQL 1–5 remains unchanged."""

MIGRATION_6 = (
    """CREATE TABLE map_objects (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, principal_id TEXT NOT NULL,
        object_id TEXT NOT NULL, object_type TEXT NOT NULL, anchor_key TEXT NOT NULL,
        reference_id TEXT, structural_label TEXT, recorded_at TEXT NOT NULL,
        creation_version TEXT NOT NULL CHECK (creation_version='object-map.v1'),
        PRIMARY KEY (tenant_id,namespace,principal_id,object_id),
        UNIQUE (tenant_id,namespace,principal_id,object_type,anchor_key),
        CHECK (length(anchor_key)=64),
        CHECK (structural_label IS NULL OR object_type IN ('owner','domain','topic','session'))
    ) WITHOUT ROWID""",
    """CREATE INDEX map_objects_type ON map_objects
       (tenant_id,namespace,principal_id,object_type,object_id)""",
    """CREATE TABLE map_proofs (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, principal_id TEXT NOT NULL,
        proof_id TEXT NOT NULL, object_id TEXT NOT NULL,
        memory_id TEXT NOT NULL, event_id TEXT NOT NULL,
        span_start INTEGER NOT NULL CHECK (span_start>=0),
        span_end INTEGER NOT NULL CHECK (span_end>span_start),
        label TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 160),
        label_start INTEGER, label_end INTEGER,
        semantic_role TEXT NOT NULL, assertion_kind TEXT NOT NULL,
        basis TEXT NOT NULL CHECK (basis IN ('source_span','derived_navigation','existing_graph')),
        recorded_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id,namespace,principal_id,proof_id),
        FOREIGN KEY (tenant_id,namespace,principal_id,object_id)
          REFERENCES map_objects(tenant_id,namespace,principal_id,object_id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id,namespace,memory_id,event_id)
          REFERENCES memory_sources(tenant_id,namespace,memory_id,event_id) ON DELETE CASCADE,
        CHECK ((label_start IS NULL)=(label_end IS NULL)),
        CHECK (label_start IS NULL OR (label_start>=span_start AND label_end<=span_end AND label_end>label_start))
    ) WITHOUT ROWID""",
    """CREATE INDEX map_proofs_object ON map_proofs
       (tenant_id,namespace,principal_id,object_id,proof_id)""",
    """CREATE INDEX map_proofs_source ON map_proofs
       (tenant_id,namespace,event_id,principal_id,proof_id)""",
    """CREATE TABLE map_memberships (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, principal_id TEXT NOT NULL,
        parent_id TEXT NOT NULL, child_id TEXT NOT NULL, role TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id,namespace,principal_id,parent_id,child_id),
        FOREIGN KEY (tenant_id,namespace,principal_id,parent_id)
          REFERENCES map_objects(tenant_id,namespace,principal_id,object_id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id,namespace,principal_id,child_id)
          REFERENCES map_objects(tenant_id,namespace,principal_id,object_id) ON DELETE CASCADE,
        CHECK (parent_id<>child_id)
    ) WITHOUT ROWID""",
    """CREATE INDEX map_memberships_children ON map_memberships
       (tenant_id,namespace,principal_id,child_id,parent_id)""",
    """CREATE TABLE map_relations (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, principal_id TEXT NOT NULL,
        relation_id TEXT NOT NULL, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
        relationship_type TEXT NOT NULL, semantic_role TEXT NOT NULL,
        basis TEXT NOT NULL CHECK (basis IN ('source_span','derived_context','existing_graph')),
        status TEXT NOT NULL, proof_count INTEGER NOT NULL CHECK (proof_count BETWEEN 1 AND 16),
        recorded_at TEXT NOT NULL, valid_from TEXT, valid_until TEXT, graph_edge_id TEXT,
        PRIMARY KEY (tenant_id,namespace,principal_id,relation_id),
        FOREIGN KEY (tenant_id,namespace,principal_id,source_id)
          REFERENCES map_objects(tenant_id,namespace,principal_id,object_id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id,namespace,principal_id,target_id)
          REFERENCES map_objects(tenant_id,namespace,principal_id,object_id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id,namespace,graph_edge_id)
          REFERENCES memory_edges(tenant_id,namespace,edge_id),
        CHECK (source_id<>target_id),
        CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_until>valid_from)
    ) WITHOUT ROWID""",
    """CREATE INDEX map_relations_outgoing ON map_relations
       (tenant_id,namespace,principal_id,source_id,relation_id)""",
    """CREATE INDEX map_relations_incoming ON map_relations
       (tenant_id,namespace,principal_id,target_id,relation_id)""",
    """CREATE TABLE map_relation_proofs (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, principal_id TEXT NOT NULL,
        relation_id TEXT NOT NULL, proof_id TEXT NOT NULL,
        PRIMARY KEY (tenant_id,namespace,principal_id,relation_id,proof_id),
        FOREIGN KEY (tenant_id,namespace,principal_id,relation_id)
          REFERENCES map_relations(tenant_id,namespace,principal_id,relation_id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id,namespace,principal_id,proof_id)
          REFERENCES map_proofs(tenant_id,namespace,principal_id,proof_id) ON DELETE CASCADE
    ) WITHOUT ROWID""",
    """CREATE INDEX map_relation_proofs_source ON map_relation_proofs
       (tenant_id,namespace,principal_id,proof_id,relation_id)""",
    """CREATE TABLE map_membership_supports (
        tenant_id TEXT NOT NULL, namespace TEXT NOT NULL, principal_id TEXT NOT NULL,
        support_id TEXT NOT NULL, parent_id TEXT NOT NULL, child_id TEXT NOT NULL,
        proof_id TEXT NOT NULL, relation_id TEXT, recorded_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id,namespace,principal_id,support_id),
        FOREIGN KEY (tenant_id,namespace,principal_id,parent_id,child_id)
          REFERENCES map_memberships(tenant_id,namespace,principal_id,parent_id,child_id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id,namespace,principal_id,proof_id)
          REFERENCES map_proofs(tenant_id,namespace,principal_id,proof_id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id,namespace,principal_id,relation_id)
          REFERENCES map_relations(tenant_id,namespace,principal_id,relation_id) ON DELETE CASCADE
    ) WITHOUT ROWID""",
    """CREATE INDEX map_membership_supports_link ON map_membership_supports
       (tenant_id,namespace,principal_id,parent_id,child_id,support_id)""",
)

OBJECTS_6 = {
    ("table", "map_objects"), ("index", "map_objects_type"),
    ("table", "map_proofs"), ("index", "map_proofs_object"), ("index", "map_proofs_source"),
    ("table", "map_memberships"), ("index", "map_memberships_children"),
    ("table", "map_relations"), ("index", "map_relations_outgoing"), ("index", "map_relations_incoming"),
    ("table", "map_relation_proofs"), ("index", "map_relation_proofs_source"),
    ("table", "map_membership_supports"), ("index", "map_membership_supports_link"),
}
