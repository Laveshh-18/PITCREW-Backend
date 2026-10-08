from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app import db
from app.repositories import refdata
from app.security import limit_plan
from app.serialization import ok
from app.services import ingest
from core.compare import compare
from core.constants import MAX_CREWS
from core.models import POI
from core.priority import rank_queue
from core.scheduler import fcfs_plan, plan_day

router = APIRouter(prefix="/v1")


@router.get("/queue")
def queue(ward_id: Optional[str] = None, limit: int = Query(100, ge=1, le=500)):
    now = ingest.utcnow()
    with db.connection() as conn:
        potholes, crews = ingest.models_for_ranking(conn, ward_id)
    items = rank_queue(potholes, crews, now)[:limit]
    return ok({"generated_at": now, "items": items})


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    crew_count: Optional[int] = Field(None, ge=1, le=MAX_CREWS)
    include_fcfs: bool = False


@router.post("/plan")
def plan(request: Request, body: Optional[PlanIn] = None):
    limit_plan(request)                                   # computes only, never persists
    body = body or PlanIn()
    now = ingest.utcnow()
    with db.connection() as conn:
        potholes, crews = ingest.models_for_ranking(conn)
        pois = [POI(**r) for r in refdata.pois(conn)]
    n = min(body.crew_count or len(crews), MAX_CREWS, len(crews))
    crews = crews[:n]                                     # first N crews by id
    greedy = plan_day(potholes, crews, now)
    fcfs = comparison = None
    if body.include_fcfs:
        fcfs = fcfs_plan(potholes, crews, now)
        comparison = compare(greedy, fcfs, potholes, pois)
    return ok({"greedy": greedy, "fcfs": fcfs, "comparison": comparison})
