from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import db
from app.errors import ApiError
from app.repositories import refdata
from app.security import require_admin
from app.serialization import ok

router = APIRouter(prefix="/v1")


@router.get("/wards")
def wards():
    with db.connection() as conn:
        return ok(refdata.wards(conn))


@router.get("/pois")
def pois():
    with db.connection() as conn:
        return ok(refdata.pois(conn))


@router.get("/crews")
def crews():
    with db.connection() as conn:
        return ok(refdata.crews(conn))


class CrewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shift_minutes: Optional[int] = Field(None, gt=0, le=1440)
    current_lat: Optional[float] = Field(None, ge=-90, le=90)
    current_lng: Optional[float] = Field(None, ge=-180, le=180)
    minutes_used: Optional[float] = Field(None, ge=0)

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if any(getattr(self, k) is None for k in self.model_fields_set):
            raise ValueError("fields cannot be null")
        return self


@router.patch("/crews/{crew_id}", dependencies=[Depends(require_admin)])
def patch_crew(crew_id: str, body: CrewPatch):
    changes = {k: getattr(body, k) for k in body.model_fields_set}  # keys come from the model, never from the client
    sets = ", ".join(col + " = %(" + col + ")s" for col in changes)
    with db.connection() as conn:
        if not refdata.crew(conn, crew_id):
            raise ApiError(404, "NOT_FOUND", "crew not found")
        conn.execute("update crews set " + sets + ", updated_at = %(now)s where id = %(id)s",
                     {**changes, "now": datetime.now(timezone.utc), "id": crew_id})
        return ok(refdata.crew(conn, crew_id))
