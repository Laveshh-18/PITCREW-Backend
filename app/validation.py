from pydantic import ValidationError

from app.errors import ApiError


def parse(model, data: dict):
    """Validate a dict (e.g. multipart fields) and turn failures into the Section 8.3 error."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first.get("loc", []))
        raise ApiError(422, "VALIDATION_ERROR", first.get("msg", "invalid value"), {"field": field})
