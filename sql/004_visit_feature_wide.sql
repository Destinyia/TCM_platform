create table if not exists mart_visit_feature_wide (
    visit_id uuid primary key references fact_visit(visit_id),
    user_id uuid not null references dim_user(user_id),
    source_vendor text not null,
    source_visit_id text not null,
    source_record_group_id text,
    visit_time timestamptz,
    visit_date date,
    visit_slot text,
    quality_status text,
    modalities jsonb not null default '[]'::jsonb,
    feature_json jsonb not null default '{}'::jsonb,
    feature_groups_json jsonb not null default '{}'::jsonb,
    feature_count integer not null default 0,
    parser_version text not null,
    updated_at timestamptz not null default now()
);

create index if not exists ix_visit_feature_wide_user_date
    on mart_visit_feature_wide (user_id, visit_date, visit_slot);

create index if not exists ix_visit_feature_wide_source
    on mart_visit_feature_wide (source_vendor, source_visit_id);

create index if not exists ix_visit_feature_wide_quality
    on mart_visit_feature_wide (quality_status);

create index if not exists ix_visit_feature_wide_feature_json
    on mart_visit_feature_wide using gin (feature_json);
