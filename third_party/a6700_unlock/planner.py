"""Read-only local-image inspection and deterministic bundle planning.

There is deliberately no apply(), USB backend or arbitrary-address device API.
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import mmap
import os
from pathlib import Path
import stat

from .catalog import Catalog


class InputError(ValueError):
    pass


class LocalImage:
    def __init__(self, path: Path, expected_size: int):
        self.path = Path(path)
        self.expected_size = expected_size

    def __enter__(self):
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise InputError("Input must be a regular local file (no devices, FIFOs or symlinks)")
        fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        try:
            self.initial = os.fstat(fd)
            if not stat.S_ISREG(self.initial.st_mode) or self.initial.st_size != self.expected_size:
                raise InputError(f"Expected regular file of {self.expected_size} bytes, got {self.initial.st_size}")
            self.file = os.fdopen(fd, "rb")
        except BaseException:
            os.close(fd)
            raise
        try:
            self.data = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        except BaseException:
            self.file.close()
            raise
        return self

    def assert_unchanged(self):
        def identity(s):
            # Some removable-volume drivers change descriptor ctime on a read
            # without changing the pathname's ctime. Use stable identity/mtime;
            # access-time bookkeeping must not invalidate read-only inspection.
            return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns
        if identity(os.fstat(self.file.fileno())) != identity(self.initial):
            raise InputError("Input changed while it was being inspected")
        if identity(self.path.lstat()) != identity(self.initial):
            raise InputError("Input path was replaced while it was being inspected")

    def __exit__(self, *unused):
        self.data.close()
        self.file.close()


def overlay_sha256(data, replacements=()) -> str:
    """Hash an overlay without modifying data or allocating a full image copy."""
    digest = hashlib.sha256()

    def span(start, end):
        for at in range(start, end, 1024 * 1024):
            digest.update(data[at:min(at + 1024 * 1024, end)])

    cursor = 0
    for offset, value in sorted(replacements):
        if offset < cursor or offset + len(value) > len(data):
            raise InputError("Overlapping/out-of-bounds hash overlay")
        span(cursor, offset)
        digest.update(value)
        cursor = offset + len(value)
    span(cursor, len(data))
    return digest.hexdigest()


def _combined_state(states):
    active = [s for s in states if s != "neutral"]
    if "unknown" in active:
        return "unknown"
    if active and all(s == "enabled" for s in active):
        return "enabled"
    if active and all(s == "disabled" for s in active):
        return "disabled"
    return "partial"


def analyze(catalog: Catalog, paths: dict[str, Path], action: str = "inspect") -> dict:
    if action not in ("inspect", "unlock", "close"):
        raise InputError("Unsupported offline action")
    if set(paths) != set(catalog.data["images"]):
        raise InputError("All catalog images are required; no partial-image planning")
    result = {
        "schema_version": 1, "catalog_id": catalog.data["catalog_id"],
        "catalog_sha256": catalog.digest, "bundle_version": catalog.data["bundle_version"],
        "model": catalog.data["model"], "firmware": catalog.data["firmware"],
        "action": action, "scope": catalog.data["scope"],
        "device_access": False, "device_writes": False, "executable_on_device": False,
        "limitations": catalog.data.get("limitations", []),
        "images": {}, "features": [], "issues": [], "changes": [], "sectors": [],
    }
    observations = []
    with ExitStack() as stack:
        opened = {key: stack.enter_context(LocalImage(paths[key], spec["size"]))
                  for key, spec in catalog.data["images"].items()}
        for image, source in opened.items():
            spec = catalog.data["images"][image]
            edits = [e for e in catalog.edits if e.image == image]
            actual_hash = overlay_sha256(source.data)
            normalized = overlay_sha256(source.data, [(e.offset, e.disabled) for e in edits])
            identity_ok = normalized == spec["normalized_sha256"]
            result["images"][image] = {
                "size": len(source.data), "view": spec["view"], "input_sha256": actual_hash,
                "normalized_sha256": normalized, "identity_matches": identity_ok,
            }
            if not identity_ok:
                result["issues"].append({"kind": "identity-mismatch", "image": image,
                                         "message": "Unmanaged content differs from the pinned offline baseline"})
            for edit in edits:
                value = source.data[edit.offset:edit.end]
                state = edit.state(value)
                observations.append((edit, value, state))
                if state == "unknown":
                    result["issues"].append({"kind": "unknown-value", "image": image,
                                             "edit_id": edit.id, "offset": edit.offset,
                                             "actual": value.hex(),
                                             "accepted": [v.hex() for v in edit.known_values]})
        for feature in catalog.data["features"]:
            states = [s for e, _, s in observations if e.feature == feature["id"]]
            result["features"].append({**feature, "id": feature["id"], "name": feature["name"],
                                        "state": _combined_state(states),
                                        "field_states": {s: states.count(s) for s in sorted(set(states))}})
        result["compatible"] = not result["issues"]
        result["bundle_state"] = (_combined_state([s for _, _, s in observations])
                                    if result["compatible"] else "unknown")
        if action != "inspect" and result["compatible"]:
            replacements = {key: [] for key in opened}
            sector_overlays = {}
            for edit, value, state in observations:
                if edit.feature not in catalog.available_features:
                    continue
                target = edit.enabled if action == "unlock" else edit.disabled
                if value == target:
                    continue
                change = {"edit_id": edit.id, "feature": edit.feature, "image": edit.image,
                          "offset": edit.offset, "length": len(value), "state_before": state,
                          "before": value.hex(), "after": target.hex(), "purpose": edit.purpose,
                          "changed_bytes": sum(a != b for a, b in zip(value, target))}
                result["changes"].append(change)
                replacements[edit.image].append((edit.offset, target))
                for absolute, old, new in zip(range(edit.offset, edit.end), value, target):
                    if old == new:
                        continue
                    sector = absolute // 512
                    key = edit.image, sector
                    if key not in sector_overlays:
                        start = sector * 512
                        before = opened[edit.image].data[start:start + 512]
                        sector_overlays[key] = (before, bytearray(before), set())
                    _, after, edit_ids = sector_overlays[key]
                    after[absolute % 512] = new
                    edit_ids.add(edit.id)
            for (image, sector), (before, after, edit_ids) in sorted(sector_overlays.items()):
                result["sectors"].append({"image": image, "file_sector": sector,
                                            "file_offset": sector * 512, "length": len(before),
                                            "before_sha256": hashlib.sha256(before).hexdigest(),
                                            "after_sha256": hashlib.sha256(after).hexdigest(),
                                            "edit_ids": sorted(edit_ids)})
            for key, source in opened.items():
                result["images"][key]["projected_sha256"] = overlay_sha256(source.data, replacements[key])
        for source in opened.values():
            source.assert_unchanged()
    result["status"] = ("blocked" if not result["compatible"] else "inspected" if action == "inspect"
                         else "ready" if result["changes"] else "no-op")
    result["changed_bytes"] = sum(c["changed_bytes"] for c in result["changes"])
    result["changed_sectors"] = len(result["sectors"])
    return result
