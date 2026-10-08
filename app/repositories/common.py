import uuid


def clean(row: dict | None) -> dict | None:
    """UUID -> str so the rows can be fed straight into core models."""
    if row is None:
        return None
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in row.items()}


def clean_all(rows) -> list:
    return [clean(r) for r in rows]
