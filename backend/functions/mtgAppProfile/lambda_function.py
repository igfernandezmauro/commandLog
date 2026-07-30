import os, json
import boto3
from datetime import datetime, timezone
from decimal import Decimal
import base64

dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

USER_PROFILE_TABLE = os.environ['USER_PROFILE_TABLE']
INGEST_LAMBDA_NAME = os.environ.get("INGEST_LAMBDA_NAME")
CORS_ORIGIN = os.environ.get('CORS_ORIGIN')

table = dynamodb.Table(USER_PROFILE_TABLE)

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _claims_from_event(event: dict) -> dict:
    rc = (event or {}).get("requestContext") or {}

    jwt = (rc.get("authorizer") or {}).get("jwt") or {}
    claims = jwt.get("claims")
    if isinstance(claims, dict) and claims:
        return claims

    claims = (rc.get("authorizer") or {}).get("claims")
    if isinstance(claims, dict) and claims:
        return claims

    return {}

def get_user_key(event: dict) -> str:
    claims = _claims_from_event(event)
    sub = claims.get('sub')
    if not sub:
        raise PermissionError("Unauthorized: missing sub claim")
    return f"user#{sub}"

def json_safe(obj):
    if isinstance(obj, list):
        return [json_safe(x) for x in obj]
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj

def response(status: int, body: dict):
    headers = {"Content-Type": "application/json"}
    if CORS_ORIGIN:
        headers.update({
            "Access-Control-Allow-Origin": CORS_ORIGIN,
            "Access-Control-Allow-Headers": "authorization, content-type",
            "Access-Control-Allow-Methods": "GET, PUT, OPTIONS",
        })
    return {"statusCode": status, "headers": headers, "body": json.dumps(json_safe(body))}

def parse_body(event):
    body = event.get("body")
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body)

def lambda_handler(event, context):
    method = ((event.get("requestContext") or {}).get("http") or {}).get("method") or event.get("httpMethod")
    if method == "OPTIONS":
        return response(200, {})

    try:
        user_key = get_user_key(event)
    except PermissionError as e:
        return response(401, {"error": str(e)})

    if method == "GET":
        resp = table.get_item(Key={"user_key": user_key}, ConsistentRead=True)
        item = resp.get("Item") or {}

        profile = {
            "user_key": user_key,
            "archidekt_username": item.get("archidekt_username", ""),
            "moxfield_username": item.get("moxfield_username", ""),
            "ingestion_enabled": bool(item.get("ingestion_enabled", False)),
            "ingestion_source": item.get("ingestion_source", ""),
            "updated_at": item.get("updated_at"),
            "created_at": item.get("created_at"),
        }
        return response(200, {"profile": profile})

    if method == "PUT":
        data = parse_body(event)

        archidekt_username = (data.get("archidekt_username") or "").strip()
        moxfield_username = (data.get("moxfield_username") or "").strip()
        ingestion_enabled = bool(data.get("ingestion_enabled", False))
        ingestion_source = (data.get("source") or "").strip()

        item = {
            "user_key": user_key,
            "archidekt_username": archidekt_username,
            "moxfield_username": moxfield_username,
            "ingestion_enabled": ingestion_enabled,
            "ingestion_enabled_key": "1" if ingestion_enabled else "0",
            "ingestion_source": ingestion_source,
            "updated_at": now_iso(),
        }

        existing = table.get_item(Key={"user_key": user_key}, ConsistentRead=True).get("Item")
        if not existing or "created_at" not in existing:
            item["created_at"] = now_iso()
        else:
            item["created_at"] = existing["created_at"]

        table.put_item(Item=item)

        started_ingest = False
        ingest_error = None

        if INGEST_LAMBDA_NAME and ingestion_enabled and ((ingestion_source == "archidekt" and archidekt_username) or (ingestion_source == "moxfield" and moxfield_username)):
            try:
                lambda_client.invoke(
                    FunctionName=INGEST_LAMBDA_NAME,
                    InvocationType="Event",
                    Payload=json.dumps({
                        "trigger": "profile_save",
                        "user_key": user_key,
                        "ingestion_source": ingestion_source,
                        "archidekt_username": archidekt_username,
                        "moxfield_username": moxfield_username,
                    }).encode("utf-8")
                )
                started_ingest = True
            except Exception as e:
                ingest_error = str(e)
        print("started:", started_ingest, "error:", ingest_error)
        return response(200, {
            "profile": item,
            "ingest": {
                "started": started_ingest,
                "error": ingest_error,
            }
        })
    
    return response(405, {"error": f"Method not allowed: {method}"})
