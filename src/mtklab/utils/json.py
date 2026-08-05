"""Centralized JSON serialization and deserialization."""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
import uuid


class _CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for UUIDs, Datetimes, Enums, and Paths."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)


def dumps(obj: Any, **kwargs: Any) -> str:
    """
    Serialize an object to a JSON formatted string.
    Automatically handles UUIDs, datetimes, Enums, and Paths.
    """
    kwargs.setdefault("cls", _CustomJSONEncoder)
    kwargs.setdefault("separators", (",", ":"))
    return json.dumps(obj, **kwargs)


def loads(s: str | bytes, **kwargs: Any) -> Any:
    """
    Deserialize a JSON formatted string to a Python object.
    """
    if not s:
        return None
    return json.loads(s, **kwargs)


def dump(obj: Any, fp: Any, **kwargs: Any) -> None:
    """
    Serialize an object as a JSON formatted stream to fp.
    """
    kwargs.setdefault("cls", _CustomJSONEncoder)
    json.dump(obj, fp, **kwargs)


def load(fp: Any, **kwargs: Any) -> Any:
    """
    Deserialize a JSON formatted stream to a Python object.
    """
    return json.load(fp, **kwargs)
