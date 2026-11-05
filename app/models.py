from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Index, #索引update测试
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Provider(Base):
    __tablename__ = "providers"

    npi: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    specialty: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)


class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    bene_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    birth_year: Mapped[int] = mapped_column(Integer, nullable=False)
    sex: Mapped[str] = mapped_column(String(1), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)


class Claim(Base):
    __tablename__ = "claims"
    # 索引update测试
    __table_args__ = (
        Index("ix_claims_npi_service_date", "npi", "service_date"),
        Index("ix_claims_service_date", "service_date"),
    )
    claim_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    bene_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("beneficiaries.bene_id"), nullable=False
    )
    npi: Mapped[str] = mapped_column(
        String(10), ForeignKey("providers.npi"), nullable=False
    )
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    diagnosis_code: Mapped[str | None] = mapped_column(String(10), nullable=True)


class ClaimLine(Base):
    __tablename__ = "claim_lines"
    __table_args__ = (
        CheckConstraint("units > 0", name="ck_lines_units_positive"),
        CheckConstraint("billed_amount >= 0", name="ck_lines_billed_nonneg"),
        CheckConstraint("paid_amount >= 0", name="ck_lines_paid_nonneg"),
    )

    claim_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("claims.claim_id"), primary_key=True
    )
    line_num: Mapped[int] = mapped_column(Integer, primary_key=True)
    hcpcs_code: Mapped[str] = mapped_column(String(10), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    billed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class ProviderRiskScore(Base):
    __tablename__ = "provider_risk_scores"

    npi: Mapped[str] = mapped_column(
        String(10), ForeignKey("providers.npi"), primary_key=True
    )
    period: Mapped[date] = mapped_column(Date, primary_key=True)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    reasons: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


from datetime import datetime  # noqa: E402
from sqlalchemy import BigInteger, DateTime, UniqueConstraint, func  # noqa: E402


class RejectedRow(Base):
    __tablename__ = "rejected_rows"
    __table_args__ = (
        UniqueConstraint("source_table", "row_hash", name="uq_rejected_source_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_table: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_row: Mapped[dict] = mapped_column(JSONB, nullable=False)
    row_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    rejected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
