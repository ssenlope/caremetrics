from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ClaimOut, ClaimPage, ProviderSummary

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/{npi}", response_model=ProviderSummary)
def get_provider(npi: str, db: Session = Depends(get_db)):
    # Grain: claims are header-level, lines are detail-level.
    # claim_count must be COUNT(DISTINCT claim_id); COUNT(*) would count lines.
    row = db.execute(
        text("""
            SELECT p.npi, p.name, p.specialty, p.state,
                   COUNT(DISTINCT c.claim_id)            AS claim_count,
                   COUNT(l.line_num)                     AS line_count,
                   COALESCE(SUM(l.billed_amount), 0)     AS total_billed,
                   COALESCE(SUM(l.paid_amount), 0)       AS total_paid
            FROM providers p
            LEFT JOIN claims c       ON c.npi = p.npi
            LEFT JOIN claim_lines l  ON l.claim_id = c.claim_id
            WHERE p.npi = :npi
            GROUP BY p.npi, p.name, p.specialty, p.state
        """),
        {"npi": npi},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="provider not found")
    return ProviderSummary(**row._mapping)


@router.get("/{npi}/claims", response_model=ClaimPage)
def provider_claims(
    npi: str,
    start: date | None = None,
    end: date | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    exists = db.execute(text("SELECT 1 FROM providers WHERE npi = :npi"), {"npi": npi}).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="provider not found")

    where = ["c.npi = :npi"]
    params: dict = {"npi": npi}
    if start is not None:
        where.append("c.service_date >= :start")
        params["start"] = start
    if end is not None:
        where.append("c.service_date <= :end")
        params["end"] = end
    where_sql = " AND ".join(where)

    total = db.execute(
        text(f"SELECT COUNT(*) FROM claims c WHERE {where_sql}"), params
    ).scalar_one()

    rows = db.execute(
        text(f"""
            SELECT c.claim_id, c.bene_id, c.service_date, c.diagnosis_code,
                   COUNT(l.line_num)                 AS line_count,
                   COALESCE(SUM(l.billed_amount), 0) AS total_billed,
                   COALESCE(SUM(l.paid_amount), 0)   AS total_paid
            FROM claims c
            LEFT JOIN claim_lines l ON l.claim_id = c.claim_id
            WHERE {where_sql}
            GROUP BY c.claim_id, c.bene_id, c.service_date, c.diagnosis_code
            ORDER BY c.service_date, c.claim_id
            LIMIT :size OFFSET :offset
        """),
        {**params, "size": size, "offset": (page - 1) * size},
    ).all()

    return ClaimPage(
        npi=npi, page=page, size=size, total=total,
        items=[ClaimOut(**r._mapping) for r in rows],
    )
