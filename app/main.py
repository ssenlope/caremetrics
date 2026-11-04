from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers import analytics, providers

app = FastAPI(title="CareMetrics", version="0.2.0")
app.include_router(providers.router)
app.include_router(analytics.router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
