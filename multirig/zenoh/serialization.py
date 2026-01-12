"""
JSON serialization helpers for Zenoh messages.

All messages are serialized as JSON for easy debugging and interoperability.
"""
import json
from dataclasses import asdict, is_dataclass
from typing import TypeVar, Type

from pydantic import BaseModel


T = TypeVar('T')


def serialize(obj: object) -> bytes:
    """
    Serialize an object to JSON bytes for Zenoh.
    
    Supports:
    - Pydantic models
    - Dataclasses
    - Dictionaries
    
    Args:
        obj: Object to serialize
        
    Returns:
        UTF-8 encoded JSON bytes
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump_json().encode('utf-8')
    elif is_dataclass(obj) and not isinstance(obj, type):
        return json.dumps(asdict(obj)).encode('utf-8')
    elif isinstance(obj, dict):
        return json.dumps(obj).encode('utf-8')
    else:
        raise TypeError(f"Cannot serialize {type(obj)}")


def deserialize(data: bytes, cls: Type[T]) -> T:
    """
    Deserialize JSON bytes to a typed object.
    
    Args:
        data: UTF-8 encoded JSON bytes
        cls: Target class (Pydantic model or dataclass)
        
    Returns:
        Deserialized object
    """
    json_str = data.decode('utf-8')
    
    if issubclass(cls, BaseModel):
        return cls.model_validate_json(json_str)
    elif is_dataclass(cls):
        return cls(**json.loads(json_str))
    else:
        raise TypeError(f"Cannot deserialize to {cls}")


def deserialize_dict(data: bytes) -> dict:
    """Deserialize JSON bytes to a dictionary."""
    return json.loads(data.decode('utf-8'))
