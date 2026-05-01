from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _float_value(data: dict[str, Any], key: str, default: float | None = None) -> float:
    value = data.get(key, default)
    if value is None:
        raise ValueError(f"Missing numeric field: {key}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field {key} must be a number.") from exc


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def _safe_name(value: str) -> str:
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value.strip())
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    normalized = normalized.strip(" ._")
    if not normalized or normalized.upper() in WINDOWS_RESERVED_NAMES:
        return "cad_job"
    return normalized


@dataclass(slots=True)
class Hole:
    x: float
    y: float
    diameter: float
    label: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hole":
        return cls(
            x=_float_value(data, "x"),
            y=_float_value(data, "y"),
            diameter=_float_value(data, "diameter"),
            label=str(data.get("label", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "diameter": self.diameter,
            "label": self.label,
        }


@dataclass(slots=True)
class MountingPlate:
    name: str
    length: float
    width: float
    thickness: float
    corner_radius: float = 0.0
    material: str = ""
    holes: list[Hole] = field(default_factory=list)
    export_formats: list[str] = field(default_factory=lambda: ["pdf", "svg"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MountingPlate":
        return cls(
            name=_safe_name(str(data.get("name", "mounting_plate"))),
            length=_float_value(data, "length"),
            width=_float_value(data, "width"),
            thickness=_float_value(data, "thickness"),
            corner_radius=_float_value(data, "corner_radius", 0.0),
            material=str(data.get("material", "")),
            holes=[Hole.from_dict(item) for item in data.get("holes", [])],
            export_formats=[str(item).lower() for item in data.get("export_formats", ["pdf", "svg"])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "length": self.length,
            "width": self.width,
            "thickness": self.thickness,
            "corner_radius": self.corner_radius,
            "material": self.material,
            "holes": [hole.to_dict() for hole in self.holes],
            "export_formats": list(self.export_formats),
        }


@dataclass(slots=True)
class FeatureOperation:
    id: str
    type: str
    parameters: dict[str, Any]
    constraint_policy: str = "fully_constrained"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeatureOperation":
        return cls(
            id=_safe_name(str(data.get("id", data.get("type", "feature")))),
            type=str(data.get("type", "")).lower(),
            parameters=dict(data.get("parameters", {})),
            constraint_policy=str(data.get("constraint_policy", "fully_constrained")).lower(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "parameters": dict(self.parameters),
            "constraint_policy": self.constraint_policy,
        }


@dataclass(slots=True)
class FeaturePart:
    name: str
    operations: list[FeatureOperation]
    material: str = ""
    export_formats: list[str] = field(default_factory=lambda: ["pdf", "svg"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeaturePart":
        return cls(
            name=_safe_name(str(data.get("name", "feature_part"))),
            operations=[FeatureOperation.from_dict(item) for item in data.get("operations", [])],
            material=str(data.get("material", "")),
            export_formats=[str(item).lower() for item in data.get("export_formats", ["pdf", "svg"])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "material": self.material,
            "operations": [operation.to_dict() for operation in self.operations],
            "export_formats": list(self.export_formats),
        }


@dataclass(slots=True)
class PrimitiveOperation:
    id: str
    type: str
    parameters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PrimitiveOperation":
        return cls(
            id=_safe_name(str(data.get("id", data.get("type", "primitive")))),
            type=str(data.get("type", "")).lower(),
            parameters=dict(data.get("parameters", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class PrimitivePart:
    name: str
    operations: list[PrimitiveOperation]
    material: str = ""
    export_formats: list[str] = field(default_factory=lambda: ["pdf", "svg"])
    source_kind: str = "primitive_part"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PrimitivePart":
        return cls(
            name=_safe_name(str(data.get("name", "primitive_part"))),
            operations=[PrimitiveOperation.from_dict(item) for item in data.get("operations", [])],
            material=str(data.get("material", "")),
            export_formats=[str(item).lower() for item in data.get("export_formats", ["pdf", "svg"])],
            source_kind=str(data.get("source_kind", "primitive_part")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "material": self.material,
            "source_kind": self.source_kind,
            "operations": [operation.to_dict() for operation in self.operations],
            "export_formats": list(self.export_formats),
        }


@dataclass(slots=True)
class CadJob:
    job_id: str
    kind: str
    units: str
    backend: str
    part: MountingPlate | FeaturePart | PrimitivePart

    @property
    def safe_name(self) -> str:
        return _safe_name(self.job_id)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CadJob":
        kind = str(data.get("kind", "mounting_plate"))
        if kind == "mounting_plate":
            part = MountingPlate.from_dict(data.get("part", {}))
        elif kind == "feature_part":
            part = FeaturePart.from_dict(data.get("part", {}))
        elif kind == "primitive_part":
            part = PrimitivePart.from_dict(data.get("part", {}))
        else:
            raise ValueError(f"Unsupported CAD job kind: {kind}")
        return cls(
            job_id=_safe_name(str(data.get("job_id", part.name))),
            kind=kind,
            units=str(data.get("units", "mm")).lower(),
            backend=str(data.get("backend", "auto")).lower(),
            part=part,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "backend": self.backend,
            "units": self.units,
            "part": self.part.to_dict(),
        }


def load_job(path: Path) -> CadJob:
    data = json.loads(path.read_text(encoding="utf-8"))
    return CadJob.from_dict(data)
