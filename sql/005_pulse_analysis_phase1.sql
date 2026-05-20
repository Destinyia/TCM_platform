create table if not exists dim_device (
    device_id uuid primary key,
    source_vendor text not null,
    source_device_id text not null,
    device_model text,
    sensor_type text,
    firmware_version text,
    sampling_rate numeric(10,2),
    calibration_date date,
    device_meta_json jsonb,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_device_source
    on dim_device (source_vendor, source_device_id);

create table if not exists dim_feature_variable (
    feature_name text primary key,
    display_name text not null,
    modality_type text not null,
    feature_level text not null,
    source_vendor text not null default 'standard',
    data_type text not null,
    unit text,
    category text,
    is_ml_feature boolean not null default false,
    is_quality_feature boolean not null default false,
    valid_range_json jsonb,
    description text,
    created_at timestamptz not null default now()
);

create table if not exists fact_pulse_measurement (
    measurement_id uuid primary key,
    visit_id uuid not null references fact_visit(visit_id),
    modality_record_id uuid not null references fact_modality_record(modality_record_id),
    user_id uuid not null references dim_user(user_id),
    device_id uuid references dim_device(device_id),
    source_vendor text not null,
    source_measurement_id text not null,
    start_time timestamptz,
    end_time timestamptz,
    duration_seconds numeric(10,2),
    visit_slot text,
    collection_hour numeric(6,3),
    hand_side text,
    pulse_position text,
    sampling_rate numeric(10,2),
    quality_status text,
    source_meta_json jsonb,
    feature_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_pulse_measurement_source
    on fact_pulse_measurement (modality_record_id, source_measurement_id);

create index if not exists ix_pulse_measurement_user_time
    on fact_pulse_measurement (user_id, start_time);

create index if not exists ix_pulse_measurement_device
    on fact_pulse_measurement (device_id);

create table if not exists fact_pulse_waveform_asset (
    waveform_asset_id uuid primary key,
    measurement_id uuid not null references fact_pulse_measurement(measurement_id),
    asset_id uuid references fact_file_asset(asset_id),
    channel_name text not null,
    hand_side text,
    pulse_position text,
    sample_count integer,
    sampling_rate numeric(10,2),
    storage_uri text,
    data_format text,
    file_hash text,
    preview_json jsonb,
    summary_json jsonb,
    created_at timestamptz not null default now()
);

create index if not exists ix_pulse_waveform_measurement
    on fact_pulse_waveform_asset (measurement_id);

create table if not exists fact_pulse_position_feature (
    position_feature_id uuid primary key,
    measurement_id uuid not null references fact_pulse_measurement(measurement_id),
    hand_side text,
    pulse_position text not null,
    feature_name text not null,
    feature_value numeric(18,6),
    feature_text text,
    feature_unit text,
    source_field text,
    parser_version text,
    quality_weight numeric(8,4),
    created_at timestamptz not null default now()
);

create index if not exists ix_pulse_position_feature_measurement
    on fact_pulse_position_feature (measurement_id);

create index if not exists ix_pulse_position_feature_name
    on fact_pulse_position_feature (feature_name);

create table if not exists analysis_run (
    analysis_run_id uuid primary key,
    analysis_type text not null,
    dataset_version_id uuid references dataset_version(dataset_version_id),
    code_version text,
    parameter_json jsonb,
    status text not null default 'created',
    result_summary_json jsonb,
    created_at timestamptz not null default now()
);

create table if not exists fact_pulse_measurement_quality (
    measurement_quality_id uuid primary key,
    analysis_run_id uuid not null references analysis_run(analysis_run_id),
    measurement_id uuid not null references fact_pulse_measurement(measurement_id),
    drift_severity_index numeric(8,4),
    stable_segment_ratio numeric(8,4),
    best_segment_start_time numeric(10,3),
    best_segment_end_time numeric(10,3),
    best_segment_quality_score numeric(8,4),
    signal_quality_score numeric(8,4),
    measurement_validity_label text,
    result_json jsonb,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_pulse_measurement_quality_run
    on fact_pulse_measurement_quality (analysis_run_id, measurement_id);

create table if not exists fact_pulse_feature_reliability (
    feature_reliability_id uuid primary key,
    analysis_run_id uuid not null references analysis_run(analysis_run_id),
    feature_name text not null,
    drift_sensitivity numeric(8,4),
    device_sensitivity numeric(8,4),
    within_session_cv numeric(8,4),
    within_session_icc numeric(8,4),
    repeatability_icc numeric(8,4),
    missing_rate numeric(8,4),
    outlier_rate numeric(8,4),
    quality_dependency_score numeric(8,4),
    feature_reliability_grade text,
    result_json jsonb,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_pulse_feature_reliability_run
    on fact_pulse_feature_reliability (analysis_run_id, feature_name);
