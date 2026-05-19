create table if not exists fact_quality_event (
    quality_event_id uuid primary key,
    entity_type text not null,
    entity_id text not null,
    quality_flag text not null,
    severity text not null,
    status text not null default 'open',
    rule_version text,
    evidence_json jsonb,
    created_at timestamptz not null default now()
);

create index if not exists ix_quality_event_entity
    on fact_quality_event (entity_type, entity_id);

create index if not exists ix_quality_event_flag
    on fact_quality_event (quality_flag, status);

create table if not exists dataset_version (
    dataset_version_id uuid primary key,
    dataset_id text not null,
    version_name text not null,
    task_type text not null,
    status text not null,
    modality_filter_json jsonb,
    quality_filter_json jsonb,
    split_strategy text,
    summary_json jsonb,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_dataset_version_name
    on dataset_version (dataset_id, version_name);


