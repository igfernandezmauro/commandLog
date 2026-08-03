from typing import Any

def claims_from_event(event: dict[str, Any] | None) -> dict[str, Any]:
    request_context = (event or {}).get("requestContext") or {}
    authorizer = request_context.get("authorizer") or {}

    jwt = authorizer.get("jwt") or {}
    claims = jwt.get("claims")

    if isinstance(claims, dict) and claims:
        return claims

    claims = authorizer.get("claims")

    if isinstance(claims, dict) and claims:
        return claims

    return {}

def get_user_key(event: dict[str, Any] | None) -> str:
    sub = claims_from_event(event).get("sub")

    if not sub:
        raise PermissionError("Unauthorized: Missing sub claim")

    return f"user#{sub}"