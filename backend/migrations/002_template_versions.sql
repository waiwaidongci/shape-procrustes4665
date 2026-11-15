-- Template versioning and point-wise migration across shared collections.
-- Idempotent-ish companion to 001_initial.sql; create_all builds the same tables
-- on fresh databases, this file documents the production DDL.

CREATE TABLE template_versions (
    id SERIAL NOT NULL,
    template_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    labels JSON NOT NULL,
    points JSON NOT NULL,
    convention VARCHAR(1200) NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_by VARCHAR(160) NOT NULL DEFAULT '',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(template_id) REFERENCES templates (id),
    UNIQUE (template_id, version)
);

CREATE UNIQUE INDEX uq_template_active
    ON template_versions (template_id)
    WHERE is_active;

CREATE TABLE template_migrations (
    id SERIAL NOT NULL,
    name VARCHAR(140) NOT NULL,
    template_id INTEGER NOT NULL,
    from_version_id INTEGER NOT NULL,
    to_version_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    label_mapping JSON NOT NULL,
    point_mapping JSON NOT NULL,
    summary JSON NOT NULL,
    created_by VARCHAR(160) NOT NULL DEFAULT '',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (id),
    UNIQUE (name),
    FOREIGN KEY(template_id) REFERENCES templates (id),
    FOREIGN KEY(from_version_id) REFERENCES template_versions (id),
    FOREIGN KEY(to_version_id) REFERENCES template_versions (id)
);

-- At most one open migration per template (draft/in_progress/conflict).
CREATE UNIQUE INDEX uq_template_open_migration
    ON template_migrations (template_id)
    WHERE status IN ('draft','in_progress','conflict');

CREATE TABLE template_migration_items (
    id SERIAL NOT NULL,
    migration_id INTEGER NOT NULL,
    specimen_id INTEGER NOT NULL,
    collection_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    before_points JSON NOT NULL,
    after_points JSON NOT NULL,
    source_specimen_version INTEGER NOT NULL,
    source_specimen_revision INTEGER NOT NULL DEFAULT 1,
    message VARCHAR(600) NOT NULL DEFAULT '',
    PRIMARY KEY (id),
    UNIQUE (migration_id, specimen_id),
    FOREIGN KEY(migration_id) REFERENCES template_migrations (id),
    FOREIGN KEY(specimen_id) REFERENCES shape_specimens (id),
    FOREIGN KEY(collection_id) REFERENCES shape_collections (id)
);

ALTER TABLE shape_specimens ADD COLUMN template_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE shape_specimens ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;

-- First-version guide for pre-existing data.
INSERT INTO template_versions (template_id, version, labels, points, convention, is_active, created_by, created_at)
SELECT id, 1, labels, points, convention, TRUE, 'system-bootstrap', CURRENT_TIMESTAMP
FROM templates
WHERE NOT EXISTS (SELECT 1 FROM template_versions tv WHERE tv.template_id = templates.id);
