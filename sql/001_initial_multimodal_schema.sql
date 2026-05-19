create table if not exists dim_user (
    user_id uuid primary key,
    cohort_id text,
    canonical_name text not null,
    sex text,
    birth_date date,
    primary_phone text,
    status text default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_dim_user_name_phone
    on dim_user (canonical_name, primary_phone);

create table if not exists dim_user_identity_map (
    identity_map_id uuid primary key,
    user_id uuid not null references dim_user(user_id),
    source_vendor text not null,
    raw_name text,
    canonical_name text not null,
    phone text,
    source_user_key text not null,
    confidence numeric(5,4),
    is_manual_verified boolean not null default false,
    rule_version text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_identity_source_key
    on dim_user_identity_map (source_vendor, source_user_key);

create table if not exists fact_visit (
    visit_id uuid primary key,
    user_id uuid not null references dim_user(user_id),
    source_vendor text not null,
    source_visit_id text not null,
    source_user_key text,
    visit_time timestamptz,
    visit_date date,
    visit_slot text,
    visit_sequence_in_day integer,
    quality_status text,
    is_complete_visit boolean,
    missing_modalities jsonb,
    is_suspected_cheat boolean default false,
    cheat_types jsonb,
    duplicate_numeric_flag boolean default false,
    duplicate_numeric_type text,
    duplicate_partner_visit_id uuid,
    time_gap_from_prev_minutes numeric(10,2),
    rule_version text,
    pipeline_version text,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_visit_source
    on fact_visit (source_vendor, source_visit_id);

create index if not exists ix_visit_user_date
    on fact_visit (user_id, visit_date, visit_slot);

create table if not exists fact_modality_record (
    modality_record_id uuid primary key,
    visit_id uuid not null references fact_visit(visit_id),
    modality_type text not null,
    source_vendor text not null,
    exists_flag boolean not null default true,
    is_required boolean,
    is_complete boolean,
    completion_status text,
    parsed_structured_data_json jsonb,
    feature_summary_json jsonb,
    numeric_fingerprint text,
    quality_flags_json jsonb,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_visit_modality
    on fact_modality_record (visit_id, modality_type, source_vendor);

create table if not exists fact_file_asset (
    asset_id uuid primary key,
    visit_id uuid references fact_visit(visit_id),
    modality_record_id uuid references fact_modality_record(modality_record_id),
    asset_type text,
    asset_role text,
    file_name text,
    file_path text,
    storage_uri text,
    file_hash text,
    file_size bigint,
    mime_type text,
    created_at_from_file timestamptz,
    parsed_success_flag boolean,
    created_at timestamptz not null default now()
);

create index if not exists ix_asset_visit
    on fact_file_asset (visit_id);

create table if not exists mart_user_day_panel (
    panel_id uuid primary key,
    user_id uuid not null references dim_user(user_id),
    visit_date date not null,
    visit_slot text not null,
    primary_visit_id uuid references fact_visit(visit_id),
    device_count integer,
    available_modalities jsonb,
    quality_status text,
    is_complete_visit boolean,
    is_suspected_cheat boolean,
    duplicate_numeric_flag boolean,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_user_day_slot
    on mart_user_day_panel (user_id, visit_date, visit_slot);

