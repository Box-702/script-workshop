"""YAML <-> JSON helpers using ruamel.yaml (round-trip safe)."""
from __future__ import annotations

from io import StringIO
from typing import Any

from ruamel.yaml import YAML

_yaml = YAML(typ="rt")
_yaml.indent(mapping=2, sequence=4, offset=2)
_yaml.preserve_quotes = True
_yaml.width = 4096


def to_yaml(data: Any) -> str:
    buf = StringIO()
    _yaml.dump(data, buf)
    return buf.getvalue()


def from_yaml(text: str) -> Any:
    return _yaml.load(text)
