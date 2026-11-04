from datetime import date

from pydantic import BaseModel


class ProviderSummary(BaseModel):
    npi: str
    name: str
    specialty: str
    state: str
    claim_count: int
    line_count: int
    total_billed: float
    total_paid: float


class ClaimOut(BaseModel):
    claim_id: str
    bene_id: str
    service_date: date
    diagnosis_code: str | None
    line_count: int
    total_billed: float
    total_paid: float


class ClaimPage(BaseModel):
    npi: str
    page: int
    size: int
    total: int
    items: list[ClaimOut]


class ProviderVolume(BaseModel):
    npi: str
    name: str
    specialty: str
    state: str
    claim_count: int
    line_count: int
    total_billed: float


class CodePricing(BaseModel):
    hcpcs_code: str
    line_count: int
    total_units: int
    avg_unit_billed: float
    avg_unit_paid: float


class StateSpend(BaseModel):
    state: str
    provider_count: int
    claim_count: int
    line_count: int
    total_billed: float
    total_paid: float
