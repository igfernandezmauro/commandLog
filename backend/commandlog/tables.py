from functools import lru_cache
from typing import Any

from commandlog.aws import dynamodb_resource
from commandlog.config import required_env


@lru_cache(maxsize=1)
def _dynammodb() -> Any:
    return dynamodb_resource()

@lru_cache(maxsize=None)
def table_from_environment(variable_name: str) -> Any:
    table_name = required_env(variable_name)
    return _dynammodb().Table(table_name)

def deck_state_table() -> Any:
    return table_from_environment("STATE_TABLE")

def user_profile_table() -> Any:
    return table_from_environment("USERS_TABLE")

def play_events_table() -> Any:
    return table_from_environment("PLAY_EVENTS_TABLE")

def deck_change_log_table() -> Any:
    return table_from_environment("CHANGE_LOG_TABLE")

def deck_diff_table() -> Any:
    return table_from_environment("DECK_DIFF_TABLE")

def cards_dimension_table() -> Any:
    return table_from_environment("CARDS_DIM_TABLE")