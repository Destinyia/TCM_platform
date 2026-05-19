create table if not exists dim_name_alias_rule (
    alias_rule_id uuid primary key,
    rule_version text not null,
    source_vendor text,
    raw_name text not null,
    canonical_name text not null,
    is_active boolean not null default true,
    note text,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_alias_rule_version_raw_name
    on dim_name_alias_rule (rule_version, raw_name);

