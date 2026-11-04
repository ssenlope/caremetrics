from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import CodePricing, ProviderVolume, StateSpend

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/provider-monthly-volume", response_model=list[ProviderVolume])
def provider_monthly_volume(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM"),
    specialty: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    start = date.fromisoformat(month + "-01")
    end = date(start.year + (1 if start.month == 12 else 0), start.month % 12 + 1, 1)

    where = "c.service_date >= :start AND c.service_date < :end"
    params: dict = {"start": start, "end": end, "limit": limit}
    if specialty:
        where += " AND p.specialty = :specialty"
        params["specialty"] = specialty

    rows = db.execute(
        text(f"""
            SELECT p.npi, p.name, p.specialty, p.state,
                   COUNT(DISTINCT c.claim_id) AS claim_count,
                   COUNT(l.line_num)          AS line_count,
                   SUM(l.billed_amount)       AS total_billed
            FROM claims c
            JOIN providers p     ON p.npi = c.npi
            JOIN claim_lines l   ON l.claim_id = c.claim_id
            WHERE {where}
            GROUP BY p.npi, p.name, p.specialty, p.state
            ORDER BY claim_count DESC, p.npi
            LIMIT :limit
        """),
        params,
    ).all()
    return [ProviderVolume(**r._mapping) for r in rows]


@router.get("/hcpcs-pricing", response_model=list[CodePricing])
def hcpcs_pricing(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    # Unit-weighted average: SUM(billed)/SUM(units), not AVG of per-line prices.
    rows = db.execute(
        text("""
            SELECT hcpcs_code,
                   COUNT(*)                              AS line_count,
                   SUM(units)                            AS total_units,
                   SUM(billed_amount) / SUM(units)       AS avg_unit_billed,
                   SUM(paid_amount)   / SUM(units)       AS avg_unit_paid
            FROM claim_lines
            GROUP BY hcpcs_code
            ORDER BY avg_unit_billed DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).all()
    return [CodePricing(**r._mapping) for r in rows]


@router.get("/state-spend", response_model=list[StateSpend])
def state_spend(db: Session = Depends(get_db)):
    # State = the provider's state.
    rows = db.execute(
        text("""
            SELECT p.state,
                   COUNT(DISTINCT p.npi)       AS provider_count,
                   COUNT(DISTINCT c.claim_id)  AS claim_count,
                   COUNT(l.line_num)           AS line_count,
                   SUM(l.billed_amount)        AS total_billed,
                   SUM(l.paid_amount)          AS total_paid
            FROM claims c
            JOIN providers p    ON p.npi = c.npi
            JOIN claim_lines l  ON l.claim_id = c.claim_id
            GROUP BY p.state
            ORDER BY total_paid DESC
        """)
    ).all()
    return [StateSpend(**r._mapping) for r in rows]
