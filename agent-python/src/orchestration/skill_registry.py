"""Domain-scoped Skill registry.

Skills are contextual guidance, not executable authority.  They are selected
after capability routing and never replace the Action Catalog, compiler,
permission checks or workflow state machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_FRONT_MATTER = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class SkillSpec:
    skill_id: str
    capability_id: str
    action_families: tuple[str, ...]
    version: str
    description: str
    path: Path


def _front_matter(text: str) -> dict[str, str]:
    match = _FRONT_MATTER.match(text)
    if not match:
        return {}
    values: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _list_value(value: str) -> tuple[str, ...]:
    text = str(value or "").strip().strip("[]")
    if not text:
        return ()
    return tuple(
        item.strip().strip("\"'")
        for item in text.split(",")
        if item.strip().strip("\"'")
    )


class SkillRegistry:
    """Discover and load only the Skill matching a routed domain/action."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2] / "skills"

    def specs(self) -> tuple[SkillSpec, ...]:
        if not self.root.exists():
            return ()
        values: list[SkillSpec] = []
        for path in sorted(self.root.glob("*/SKILL.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            metadata = _front_matter(text)
            skill_id = metadata.get("skill_id") or metadata.get("name") or path.parent.name
            capability = metadata.get("capability_id") or ""
            if not capability:
                continue
            values.append(
                SkillSpec(
                    skill_id=skill_id,
                    capability_id=capability,
                    action_families=_list_value(metadata.get("action_families", "")),
                    version=metadata.get("version") or "1",
                    description=metadata.get("description") or "",
                    path=path,
                )
            )
        return tuple(values)

    def for_capability(self, capability_id: str | None) -> tuple[SkillSpec, ...]:
        value = str(capability_id or "").strip()
        return tuple(
            item
            for item in self.specs()
            if value in {part.strip() for part in item.capability_id.split(",") if part.strip()}
        )

    def select(self, capability_id: str | None, action_id: str | None = None) -> SkillSpec | None:
        candidates = self.for_capability(capability_id)
        if not candidates:
            return None
        action = str(action_id or "").strip()
        if action:
            matching = [
                item for item in candidates
                if not item.action_families or action in item.action_families
            ]
            if matching:
                return matching[0]
        return candidates[0]

    def prompt_for(self, capability_id: str | None, *, action_id: str | None = None) -> str:
        spec = self.select(capability_id, action_id)
        if spec is None:
            return ""
        try:
            text = spec.path.read_text(encoding="utf-8")
        except OSError:
            return ""
        body = _FRONT_MATTER.sub("", text, count=1).strip()
        if not body:
            return ""
        return (
            f"当前领域 Skill：{spec.skill_id}（版本 {spec.version}）。"
            "Skill 只提供领域语义和澄清方法，不能替代 Action Catalog、权限、状态机或编译器。\n"
            f"{body}"
        )

    def version_for(self, capability_id: str | None, *, action_id: str | None = None) -> str | None:
        spec = self.select(capability_id, action_id)
        return spec.version if spec else None

    def files(self) -> dict[str, str]:
        """Return all Skill files for the StateBackend without enabling them."""
        files: dict[str, str] = {}
        for spec in self.specs():
            try:
                files[f"/skills/{spec.path.parent.name}/SKILL.md"] = spec.path.read_text(encoding="utf-8")
            except OSError:
                continue
        return files

    def source_paths(self, capability_id: str | None) -> list[str]:
        return [f"/skills/{item.path.parent.name}/" for item in self.for_capability(capability_id)]


skill_registry = SkillRegistry()


__all__ = ["SkillRegistry", "SkillSpec", "skill_registry"]
