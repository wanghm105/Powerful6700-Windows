"""Pinned, sparse physical layout for supported patch targets and guards."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib.resources import files
import json

from .catalog import Catalog, CatalogError
from .planner import _combined_state

# Supported camera-side block devices, in profile order. Shipped profiles use
# the first two; the optional third device targets the CP firmware partition.
KNOWN_DEVICES = ("/dev/nflasha15", "/dev/nflasha5", "/dev/nflasha8")
DEVICE_SECTORS = {0: 0x165800, 1: 0x96000, 2: 48844}
IMAGE_DEVICES = {"app": 0, "wbi": 1, "cpapp": 2}
PLAIN_IMAGES = {"wbi", "cpapp"}


@dataclass(frozen=True)
class DeviceProfile:
    data: dict
    digest: str
    catalog: Catalog

    @classmethod
    def from_dict(cls, data, catalog):
        schema = data.get("schema_version")
        devices = data.get("devices")
        if (schema not in (1, 2) or data.get("sector_size") != 512
                or not isinstance(devices, list) or not 1 <= len(devices) <= len(KNOWN_DEVICES)
                or list(devices) != list(KNOWN_DEVICES[:len(devices)])
                or data.get("catalog_sha256") != catalog.digest):
            raise CatalogError("Unsupported or mismatched device profile")
        entries = data.get("entries", [])
        if not entries or len(entries) > 512:
            raise CatalogError("Invalid sparse target/guard count")
        keys, covered = set(), {}
        known = {e.id: e for e in catalog.edits}
        for index, row in enumerate(entries):
            if (row.get("index") != index or type(row.get("device")) is not int
                    or not 0 <= row["device"] < len(devices) or type(row.get("device_offset")) is not int
                    or row["device_offset"] < 0 or row["device_offset"] % 512):
                raise CatalogError("Invalid device target address/index")
            limit = DEVICE_SECTORS[row["device"]] * 512
            if row["device_offset"] + 512 > limit:
                raise CatalogError("Target outside supported partition")
            key = row["device"], row["device_offset"]
            if key in keys:
                raise CatalogError("Duplicate device sector")
            keys.add(key)
            if row.get("role") == "target":
                image, off = row.get("image"), row.get("file_offset")
                if (image not in catalog.data["images"] or type(off) is not int or off < 0 or off % 512
                        or off + 512 > catalog.data["images"][image]["size"]
                        or IMAGE_DEVICES.get(image) != row["device"]):
                    raise CatalogError("Invalid logical-to-physical target mapping")
                if image in PLAIN_IMAGES and off != row["device_offset"]:
                    raise CatalogError("Plain-image offset mapping mismatch")
                if not row.get("edit_ids"):
                    raise CatalogError("Target must be owned by catalog edits")
                for ident in row["edit_ids"]:
                    e = known.get(ident)
                    if not e or e.image != image or not (e.offset < off + 512 and e.end > off):
                        raise CatalogError("Invalid edit-to-sector reference")
                    covered.setdefault(ident, set()).add(off)
                digest = row.get("unmanaged_sha256" if schema == 2 else "normalized_sha256", "")
                if schema == 2:
                    volatile = row.get("volatile_offsets", [])
                    if (not isinstance(volatile, list)
                            or any(type(value) is not int or not 0 <= value < 512 for value in volatile)
                            or len(set(volatile)) != len(volatile)):
                        raise CatalogError("Invalid volatile byte offsets")
                    field_bytes = set()
                    for ident in row["edit_ids"]:
                        e = known[ident]
                        start = max(e.offset, off) - off
                        end = min(e.end, off + 512) - off
                        field_bytes.update(range(start, end))
                    if set(volatile) & field_bytes:
                        raise CatalogError("Volatile byte overlaps a catalog field")
            elif row.get("role") == "guard":
                digest = row.get("sha256", "")
            else:
                raise CatalogError("Unknown sparse entry role")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise CatalogError("Invalid sparse guard SHA-256")
        for e in catalog.edits:
            if covered.get(e.id) != set(range(e.offset // 512 * 512, (e.end - 1) // 512 * 512 + 1, 512)):
                raise CatalogError("Profile does not fully cover every catalog field")
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return cls(json.loads(canonical), hashlib.sha256(canonical).hexdigest(), catalog)

    @property
    def entries(self):
        return self.data["entries"]

    def masks(self, *, writable_only=False):
        """Recognition includes parked fields; write masks exclude them entirely."""
        edits = {e.id: e for e in self.catalog.edits}
        result = []
        for row in self.entries:
            mask = bytearray(64)
            if row["role"] == "target":
                off = row["file_offset"]
                for ident in row["edit_ids"]:
                    e = edits[ident]
                    if writable_only and e.feature not in self.catalog.available_features:
                        continue
                    for at in range(max(e.offset, off), min(e.end, off + 512)):
                        relative = at - off
                        mask[relative // 8] |= 1 << (relative % 8)
            result.append(bytes(mask))
        return result


def load_device_profile(catalog):
    data = json.loads(files("a6700_unlock").joinpath("data/device-profile.json").read_text(encoding="utf-8"))
    return DeviceProfile.from_dict(data, catalog)


def _feature_selection(catalog, features):
    ids = [f["id"] for f in catalog.data["features"]]
    if features is None:
        return "all", list(catalog.available_features)
    if features == "missing":
        return "missing", list(catalog.available_features)
    if isinstance(features, str):
        features = [features]
    selected = []
    for ident in features:
        if ident not in ids:
            raise ValueError(f"Unknown feature: {ident}")
        if ident not in catalog.available_features:
            raise ValueError(f"功能暂未开放：{ident}，开发与验证尚未完成")
        if ident not in selected:
            selected.append(ident)
    if not selected:
        raise ValueError("至少选择一个功能")
    return "explicit", selected


def inspect_sectors(profile: DeviceProfile, sectors: list[bytes], action="inspect", features=None):
    if action not in ("inspect", "unlock", "close"):
        raise ValueError("Unsupported device operation")
    if len(sectors) != len(profile.entries) or any(len(s) != 512 for s in sectors):
        raise ValueError("Incomplete sparse capture")
    catalog = profile.catalog
    schema = profile.data.get("schema_version", 1)
    edits = {e.id: e for e in catalog.edits}
    index_by_file = {(r["image"], r["file_offset"]): r["index"]
                     for r in profile.entries if r["role"] == "target"}
    issues = []
    masks = profile.masks()
    for row, sector, mask in zip(profile.entries, sectors, masks):
        if row["role"] == "target":
            if schema == 2:
                # v2 pins only bytes that no catalog field owns; known feature
                # values can change independently in the same sector.
                normalized = bytearray(sector)
                for at in range(512):
                    if mask[at // 8] & (1 << (at % 8)):
                        normalized[at] = 0
                for at in row.get("volatile_offsets", []):
                    normalized[at] = 0
                expected = row["unmanaged_sha256"]
            else:
                normalized = bytearray(sector)
                off = row["file_offset"]
                for ident in row["edit_ids"]:
                    e = edits[ident]
                    start, end = max(e.offset, off), min(e.end, off + 512)
                    normalized[start - off:end - off] = e.disabled[start - e.offset:end - e.offset]
                expected = row["normalized_sha256"]
        else:
            normalized = sector
            expected = row["sha256"]
        if hashlib.sha256(normalized).hexdigest() != expected:
            issues.append(dict(kind="sector-guard-mismatch", role=row["role"],
                               index=row["index"],
                               device=profile.data["devices"][row["device"]],
                               offset=row["device_offset"]))
    observations = []
    for edit in catalog.edits:
        actual = bytes(sectors[index_by_file[(edit.image, at // 512 * 512)]][at % 512]
                       for at in range(edit.offset, edit.end))
        state = edit.state(actual)
        observations.append((edit, state))
        if state == "unknown":
            issues.append(dict(kind="unknown-field", edit_id=edit.id, image=edit.image,
                               offset=edit.offset, actual=actual.hex()))
    mode, requested = _feature_selection(catalog, features)
    states = {feature["id"]: _combined_state(
        [s for e, s in observations if e.feature == feature["id"]])
        for feature in catalog.data["features"]}
    if mode == "missing":
        goal = "enabled" if action == "unlock" else "disabled"
        selected = [feature["id"] for feature in catalog.data["features"]
                    if feature["id"] in requested and states[feature["id"]] != goal]
    else:
        selected = requested
    if action != "inspect" and not selected and mode != "missing":
        raise ValueError("所选功能没有需要修改的项")
    selected_set = set(selected)
    for feature in catalog.data["features"]:
        if feature["id"] not in selected_set:
            continue
        for required in feature.get("requires", []):
            if required not in selected_set and states.get(required) != "enabled":
                issues.append(dict(kind="feature-requirement", feature=feature["id"],
                                   requires=required, required_state=states.get(required)))
    after = [bytearray(s) for s in sectors]
    if action != "inspect":
        for edit in catalog.edits:
            if edit.feature not in selected_set:
                continue
            target = edit.enabled if action == "unlock" else edit.disabled
            for at, value in zip(range(edit.offset, edit.end), target):
                after[index_by_file[(edit.image, at // 512 * 512)]][at % 512] = value
    compatible = not issues
    if not compatible:
        after = [bytearray(s) for s in sectors]
    features_out = []
    for feature in catalog.data["features"]:
        row = {key: value for key, value in feature.items() if key not in ("id", "name")}
        row.update(id=feature["id"], name=feature["name"], state=states[feature["id"]],
                   selected=feature["id"] in selected_set)
        features_out.append(row)
    changed = [i for i in range(len(sectors)) if sectors[i] != after[i]]
    plan = dict(profile_id=profile.data["profile_id"], profile_sha256=profile.digest,
                catalog_sha256=catalog.digest, model=catalog.data["model"], firmware=catalog.data["firmware"],
                action=action, compatible=compatible, features=features_out, issues=issues,
                selection_mode=mode, selected_features=[feature["id"] for feature in catalog.data["features"]
                                                        if feature["id"] in selected_set],
                bundle_state=_combined_state([s for _, s in observations]) if compatible else "unknown",
                status="blocked" if not compatible else "inspected" if action == "inspect" else "ready" if changed else "no-op",
                read_sectors=len(sectors), read_bytes=len(sectors) * 512,
                changed_indices=changed, changed_sectors=len(changed),
                changed_bytes=sum(sum(a != b for a, b in zip(sectors[i], after[i])) for i in changed),
                hardware_validation=profile.data["hardware_validation"], full_backup=False)
    return plan, [bytes(s) for s in after]
