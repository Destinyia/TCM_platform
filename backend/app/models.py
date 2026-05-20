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
