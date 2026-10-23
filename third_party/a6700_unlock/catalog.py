"""Strict, dependency-free catalogue loading and fixed-length patch definitions."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib.resources import files
import json
import re
from typing import Any


class CatalogError(ValueError):
    pass


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise CatalogError(f"{label} must be an integer >= {minimum}")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{label} must be a non-empty string")
    return value


def _hex(value: Any, label: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9a-f]{2})+", value):
        raise CatalogError(f"{label} must be non-empty lowercase hex")
    return bytes.fromhex(value)


@dataclass(frozen=True)
class Edit:
    id: str
    image: str
    offset: int
    disabled: bytes
    enabled: bytes
    known_values: tuple[bytes, ...]
    feature: str
    purpose: str

    @property
    def end(self) -> int:
        return self.offset + len(self.disabled)

    def state(self, actual: bytes) -> str:
        if actual not in self.known_values:
            return "unknown"
        if self.disabled == self.enabled and actual == self.disabled:
            return "neutral"
        if actual == self.disabled:
            return "disabled"
        if actual == self.enabled:
            return "enabled"
        return "legacy"


@dataclass(frozen=True)
class Catalog:
    data: dict
    edits: tuple[Edit, ...]
    digest: str

    @classmethod
    def from_dict(cls, data: dict) -> Catalog:
        try:
            return cls._parse(data)
        except (KeyError, TypeError) as exc:
            raise CatalogError(f"Invalid catalog structure: {exc}") from exc

    @classmethod
    def _parse(cls, data: dict) -> Catalog:
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise CatalogError("Unsupported catalog schema_version")
        if data.get("scope") != "offline-known-snapshot-only" or data.get("device_write_supported") is not False:
            raise CatalogError("This prototype accepts offline-only catalogs")
        for key in ("catalog_id", "model", "firmware", "bundle_version"):
            _string(data[key], key)
        if data.get("sector_size") != 512:
            raise CatalogError("Only 512-byte planning units are supported")
        if not isinstance(data["features"], list) or not data["features"]:
            raise CatalogError("features must be a non-empty list")
        feature_ids = [_string(f["id"], "feature id") for f in data["features"]]
        if len(set(feature_ids)) != len(feature_ids):
            raise CatalogError("Duplicate feature id")
        for f in data["features"]:
            _string(f["name"], "feature name")
            if type(f.get("available", True)) is not bool:
                raise CatalogError("Feature available must be boolean")
            if not f.get("available", True):
                _string(f.get("unavailable_reason"), "unavailable reason")
        if not isinstance(data["images"], dict) or not data["images"]:
            raise CatalogError("images must be a non-empty object")
        for key, image in data["images"].items():
            _string(key, "image id")
            _integer(image["size"], "image size", 1)
            _string(image["view"], "image view")
            if not re.fullmatch(r"[0-9a-f]{64}", image["normalized_sha256"]):
                raise CatalogError("Invalid normalized SHA-256")
        if not isinstance(data["edits"], list) or not data["edits"]:
            raise CatalogError("edits must be a non-empty list")
        edits = []
        ids = set()
        for row in data["edits"]:
            ident = _string(row["id"], "edit id")
            if ident in ids:
                raise CatalogError(f"Duplicate edit id: {ident}")
            ids.add(ident)
            disabled, enabled = _hex(row["disabled"], ident), _hex(row["enabled"], ident)
            if not isinstance(row["known_values"], list) or not row["known_values"]:
                raise CatalogError(f"Missing known values: {ident}")
            values = tuple(_hex(v, ident) for v in row["known_values"])
            if len(enabled) != len(disabled) or any(len(v) != len(disabled) for v in values):
                raise CatalogError(f"Variable-length edit: {ident}")
            if len(set(values)) != len(values) or disabled not in values or enabled not in values:
                raise CatalogError(f"Invalid known-value set: {ident}")
            image, feature = row["image"], row["feature"]
            if image not in data["images"] or feature not in feature_ids:
                raise CatalogError(f"Unknown image/feature: {ident}")
            offset = _integer(row["offset"], "edit offset")
            if offset + len(disabled) > data["images"][image]["size"]:
                raise CatalogError(f"Edit out of bounds: {ident}")
            edits.append(Edit(ident, image, offset, disabled, enabled, values, feature,
                              _string(row["purpose"], "edit purpose")))
        edits.sort(key=lambda e: (e.image, e.offset))
        for left, right in zip(edits, edits[1:]):
            if left.image == right.image and left.end > right.offset:
                raise CatalogError(f"Overlapping edits: {left.id}, {right.id}")
        if any(not any(e.feature == f and e.disabled != e.enabled for e in edits) for f in feature_ids):
            raise CatalogError("Every feature must have at least one active edit")
        # Own a JSON copy: callers cannot invalidate the parsed object via input mutation.
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return cls(json.loads(canonical), tuple(edits), hashlib.sha256(canonical).hexdigest())

    @property
    def available_features(self) -> tuple[str, ...]:
        """Release policy; unavailable fields remain recognized but never writable."""
        return tuple(f["id"] for f in self.data["features"] if f.get("available", True))

    def summary(self) -> dict:
        return {
            "catalog_id": self.data["catalog_id"], "catalog_sha256": self.digest,
            "model": self.data["model"], "firmware": self.data["firmware"],
            "scope": self.data["scope"], "device_write_supported": False,
            "features": [dict(f, edit_count=sum(e.feature == f["id"] for e in self.edits))
                         for f in self.data["features"]],
            "images": {key: dict(value, edit_count=sum(e.image == key for e in self.edits),
                                  changed_bytes=sum(sum(a != b for a, b in zip(e.disabled, e.enabled))
                                                    for e in self.edits if e.image == key))
                       for key, value in self.data["images"].items()},
            "limitations": self.data.get("limitations", []),
        }


def load_catalog() -> Catalog:
    data = json.loads(files("a6700_unlock").joinpath("data/a6700-2.00.json").read_text(encoding="utf-8"))
    return Catalog.from_dict(data)
