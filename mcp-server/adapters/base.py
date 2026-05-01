from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class BackendUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class BackendResult:
    backend: str
    ok: bool
    artifacts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def add_artifact(self, path: Path) -> None:
        self.artifacts.append(str(path))

