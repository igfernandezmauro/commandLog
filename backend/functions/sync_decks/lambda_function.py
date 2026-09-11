import os

from commandlog.logging import get_logger
from commandlog.ingestion.sync import sync_archidekt_user, sync_enabled_profiles


logger = get_logger(__name__)


def is_dry_run() -> bool:
    return os.getenv("DRY_RUN", "false").strip().lower() == "true"

def lambda_handler(event, context):
    event = event or {}
    dry_run = is_dry_run()

    user_key = event.get("user_key")
    source = event.get("ingestion_source")
    username = event.get("archidekt_username")

    if user_key and source == "archidekt" and username:
        return sync_archidekt_user(str(user_key), str(username), dry_run=dry_run)

    logger.info("Running scheduled Archidekt ingestion")

    return sync_enabled_profiles(dry_run=dry_run)
    