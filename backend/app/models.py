from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from backend.app.database import Base


def uuid_pk() -> Column:
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "dim_user"
    __table_args__ = (UniqueConstraint("canonical_name", "primary_phone", name="uq_dim_user_name_phone"),)

    user_id = uuid_pk()
    cohort_id = Column(Text)
    canonical_name = Column(Text, nullable=False)
    sex = Column(Text)
    birth_date = Column(Date)
    primary_phone = Column(Text)
    status = Column(Text, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    identities = relationship("UserIdentityMap", back_populates="user")
    visits = relationship("Visit", back_populates="user")


class UserIdentityMap(Base):
    __tablename__ = "dim_user_identity_map"
    __table_args__ = (UniqueConstraint("source_vendor", "source_user_key", name="uq_identity_source_key"),)

    identity_map_id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("dim_user.user_id"), nullable=False)
    source_vendor = Column(Text, nullable=False)
    raw_name = Column(Text)
    canonical_name = Column(Text, nullable=False)
    phone = Column(Text)
    source_user_key = Column(Text, nullable=False)
    confidence = Column(Numeric(5, 4))
    is_manual_verified = Column(Boolean, nullable=False, default=False)
    rule_version = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="identities")


class NameAliasRule(Base):
    __tablename__ = "dim_name_alias_rule"
    __table_args__ = (UniqueConstraint("rule_version", "raw_name", name="uq_alias_rule_version_raw_name"),)

    alias_rule_id = uuid_pk()
    rule_version = Column(Text, nullable=False)
    source_vendor = Column(Text)
    raw_name = Column(Text, nullable=False)
    canonical_name = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Device(Base):
    __tablename__ = "dim_device"
    __table_args__ = (UniqueConstraint("source_vendor", "source_device_id", name="uq_device_source"),)

    device_id = uuid_pk()
    source_vendor = Column(Text, nullable=False)
    source_device_id = Column(Text, nullable=False)
    device_model = Column(Text)
    sensor_type = Column(Text)
    firmware_version = Column(Text)
    sampling_rate = Column(Numeric(10, 2))
    calibration_date = Column(Date)
    device_meta_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Visit(Base):
    __tablename__ = "fact_visit"
    __table_args__ = (UniqueConstraint("source_vendor", "source_visit_id", name="uq_visit_source"),)

    visit_id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("dim_user.user_id"), nullable=False)
    source_vendor = Column(Text, nullable=False)
    source_visit_id = Column(Text, nullable=False)
    source_user_key = Column(Text)
    visit_time = Column(DateTime(timezone=True))
    visit_date = Column(Date)
    visit_slot = Column(Text)
    visit_sequence_in_day = Column(Integer)
    quality_status = Column(Text)
    is_complete_visit = Column(Boolean)
    missing_modalities = Column(JSONB)
    is_suspected_cheat = Column(Boolean, default=False)
    cheat_types = Column(JSONB)
    duplicate_numeric_flag = Column(Boolean, default=False)
    duplicate_numeric_type = Column(Text)
    duplicate_partner_visit_id = Column(UUID(as_uuid=True))
    time_gap_from_prev_minutes = Column(Numeric(10, 2))
    rule_version = Column(Text)
    pipeline_version = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="visits")
    modalities = relationship("ModalityRecord", back_populates="visit")
    assets = relationship("FileAsset", back_populates="visit")


class ModalityRecord(Base):
    __tablename__ = "fact_modality_record"
    __table_args__ = (UniqueConstraint("visit_id", "modality_type", "source_vendor", name="uq_visit_modality"),)

    modality_record_id = uuid_pk()
    visit_id = Column(UUID(as_uuid=True), ForeignKey("fact_visit.visit_id"), nullable=False)
    modality_type = Column(Text, nullable=False)
    source_vendor = Column(Text, nullable=False)
    exists_flag = Column(Boolean, nullable=False, default=True)
    is_required = Column(Boolean)
    is_complete = Column(Boolean)
    completion_status = Column(Text)
    parsed_structured_data_json = Column(JSONB)
    feature_summary_json = Column(JSONB)
    numeric_fingerprint = Column(Text)
    quality_flags_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    visit = relationship("Visit", back_populates="modalities")


class FileAsset(Base):
    __tablename__ = "fact_file_asset"

    asset_id = uuid_pk()
    visit_id = Column(UUID(as_uuid=True), ForeignKey("fact_visit.visit_id"))
    modality_record_id = Column(UUID(as_uuid=True), ForeignKey("fact_modality_record.modality_record_id"))
    asset_type = Column(Text)
    asset_role = Column(Text)
    file_name = Column(Text)
    file_path = Column(Text)
    storage_uri = Column(Text)
    file_hash = Column(Text)
    file_size = Column(BigInteger)
    mime_type = Column(Text)
    created_at_from_file = Column(DateTime(timezone=True))
    parsed_success_flag = Column(Boolean)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    visit = relationship("Visit", back_populates="assets")


class UserDayPanel(Base):
    __tablename__ = "mart_user_day_panel"
    __table_args__ = (UniqueConstraint("user_id", "visit_date", "visit_slot", name="uq_user_day_slot"),)

    panel_id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("dim_user.user_id"), nullable=False)
    visit_date = Column(Date, nullable=False)
    visit_slot = Column(Text, nullable=False)
    primary_visit_id = Column(UUID(as_uuid=True), ForeignKey("fact_visit.visit_id"))
    device_count = Column(Integer)
    available_modalities = Column(JSONB)
    quality_status = Column(Text)
    is_complete_visit = Column(Boolean)
    is_suspected_cheat = Column(Boolean)
    duplicate_numeric_flag = Column(Boolean)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class VisitFeatureWide(Base):
    __tablename__ = "mart_visit_feature_wide"

    visit_id = Column(UUID(as_uuid=True), ForeignKey("fact_visit.visit_id"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("dim_user.user_id"), nullable=False)
    source_vendor = Column(Text, nullable=False)
    source_visit_id = Column(Text, nullable=False)
    source_record_group_id = Column(Text)
    visit_time = Column(DateTime(timezone=True))
    visit_date = Column(Date)
    visit_slot = Column(Text)
    quality_status = Column(Text)
    modalities = Column(JSONB, nullable=False, default=list)
    feature_json = Column(JSONB, nullable=False, default=dict)
    feature_groups_json = Column(JSONB, nullable=False, default=dict)
    feature_count = Column(Integer, nullable=False, default=0)
    parser_version = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FeatureVariable(Base):
    __tablename__ = "dim_feature_variable"

    feature_name = Column(Text, primary_key=True)
    display_name = Column(Text, nullable=False)
    modality_type = Column(Text, nullable=False)
    feature_level = Column(Text, nullable=False)
    source_vendor = Column(Text, nullable=False, default="standard")
    data_type = Column(Text, nullable=False)
    unit = Column(Text)
    category = Column(Text)
    is_ml_feature = Column(Boolean, nullable=False, default=False)
    is_quality_feature = Column(Boolean, nullable=False, default=False)
    valid_range_json = Column(JSONB)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PulseMeasurement(Base):
    __tablename__ = "fact_pulse_measurement"
    __table_args__ = (UniqueConstraint("modality_record_id", "source_measurement_id", name="uq_pulse_measurement_source"),)

    measurement_id = uuid_pk()
    visit_id = Column(UUID(as_uuid=True), ForeignKey("fact_visit.visit_id"), nullable=False)
    modality_record_id = Column(UUID(as_uuid=True), ForeignKey("fact_modality_record.modality_record_id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("dim_user.user_id"), nullable=False)
    device_id = Column(UUID(as_uuid=True), ForeignKey("dim_device.device_id"))
    source_vendor = Column(Text, nullable=False)
    source_measurement_id = Column(Text, nullable=False)
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    duration_seconds = Column(Numeric(10, 2))
    visit_slot = Column(Text)
    collection_hour = Column(Numeric(6, 3))
    hand_side = Column(Text)
    pulse_position = Column(Text)
    sampling_rate = Column(Numeric(10, 2))
    quality_status = Column(Text)
    source_meta_json = Column(JSONB)
    feature_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PulseWaveformAsset(Base):
    __tablename__ = "fact_pulse_waveform_asset"

    waveform_asset_id = uuid_pk()
    measurement_id = Column(UUID(as_uuid=True), ForeignKey("fact_pulse_measurement.measurement_id"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("fact_file_asset.asset_id"))
    channel_name = Column(Text, nullable=False)
    hand_side = Column(Text)
    pulse_position = Column(Text)
    sample_count = Column(Integer)
    sampling_rate = Column(Numeric(10, 2))
    storage_uri = Column(Text)
    data_format = Column(Text)
    file_hash = Column(Text)
    preview_json = Column(JSONB)
    summary_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PulsePositionFeature(Base):
    __tablename__ = "fact_pulse_position_feature"

    position_feature_id = uuid_pk()
    measurement_id = Column(UUID(as_uuid=True), ForeignKey("fact_pulse_measurement.measurement_id"), nullable=False)
    hand_side = Column(Text)
    pulse_position = Column(Text, nullable=False)
    feature_name = Column(Text, nullable=False)
    feature_value = Column(Numeric(18, 6))
    feature_text = Column(Text)
    feature_unit = Column(Text)
    source_field = Column(Text)
    parser_version = Column(Text)
    quality_weight = Column(Numeric(8, 4))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AnalysisRun(Base):
    __tablename__ = "analysis_run"

    analysis_run_id = uuid_pk()
    analysis_type = Column(Text, nullable=False)
    dataset_version_id = Column(UUID(as_uuid=True), ForeignKey("dataset_version.dataset_version_id"))
    code_version = Column(Text)
    parameter_json = Column(JSONB)
    status = Column(Text, nullable=False, default="created")
    result_summary_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PulseMeasurementQuality(Base):
    __tablename__ = "fact_pulse_measurement_quality"
    __table_args__ = (UniqueConstraint("analysis_run_id", "measurement_id", name="uq_pulse_measurement_quality_run"),)

    measurement_quality_id = uuid_pk()
    analysis_run_id = Column(UUID(as_uuid=True), ForeignKey("analysis_run.analysis_run_id"), nullable=False)
    measurement_id = Column(UUID(as_uuid=True), ForeignKey("fact_pulse_measurement.measurement_id"), nullable=False)
    drift_severity_index = Column(Numeric(8, 4))
    stable_segment_ratio = Column(Numeric(8, 4))
    best_segment_start_time = Column(Numeric(10, 3))
    best_segment_end_time = Column(Numeric(10, 3))
    best_segment_quality_score = Column(Numeric(8, 4))
    signal_quality_score = Column(Numeric(8, 4))
    measurement_validity_label = Column(Text)
    result_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PulseFeatureReliability(Base):
    __tablename__ = "fact_pulse_feature_reliability"
    __table_args__ = (UniqueConstraint("analysis_run_id", "feature_name", name="uq_pulse_feature_reliability_run"),)

    feature_reliability_id = uuid_pk()
    analysis_run_id = Column(UUID(as_uuid=True), ForeignKey("analysis_run.analysis_run_id"), nullable=False)
    feature_name = Column(Text, nullable=False)
    drift_sensitivity = Column(Numeric(8, 4))
    device_sensitivity = Column(Numeric(8, 4))
    within_session_cv = Column(Numeric(8, 4))
    within_session_icc = Column(Numeric(8, 4))
    repeatability_icc = Column(Numeric(8, 4))
    missing_rate = Column(Numeric(8, 4))
    outlier_rate = Column(Numeric(8, 4))
    quality_dependency_score = Column(Numeric(8, 4))
    feature_reliability_grade = Column(Text)
    result_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class QualityEvent(Base):
    __tablename__ = "fact_quality_event"

    quality_event_id = uuid_pk()
    entity_type = Column(Text, nullable=False)
    entity_id = Column(Text, nullable=False)
    quality_flag = Column(Text, nullable=False)
    severity = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="open")
    rule_version = Column(Text)
    evidence_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DatasetVersion(Base):
    __tablename__ = "dataset_version"

    dataset_version_id = uuid_pk()
    dataset_id = Column(Text, nullable=False)
    version_name = Column(Text, nullable=False)
    task_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    modality_filter_json = Column(JSONB)
    quality_filter_json = Column(JSONB)
    split_strategy = Column(Text)
    summary_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
