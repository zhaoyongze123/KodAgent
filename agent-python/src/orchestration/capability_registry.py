"""Sparse capability registry used by the parent intent router.

The registry exposes only domain cards to the parent prompt.  Action details
are intentionally left to ``route_conversation`` and the Java-backed Action
Catalog after a capability has been selected.
"""

from __future__ import annotations

from dataclasses import dataclass

from .capabilities import CAPABILITIES, GENERAL_CAPABILITY, canonical_capability_id


@dataclass(frozen=True)
class CapabilityCard:
    capability_id: str
    description: str
    execution_boundary: str
    fallback: str


class CapabilityRegistry:
    """Read-only projection of the capability catalog for prompt assembly."""

    def __init__(self) -> None:
        self._cards = tuple(
            CapabilityCard(
                capability_id=item.name,
                description=item.description,
                execution_boundary=item.execution_boundary,
                fallback=item.fallback,
            )
            for item in (*CAPABILITIES, GENERAL_CAPABILITY)
        )

    def cards(self) -> tuple[CapabilityCard, ...]:
        return self._cards

    def get(self, capability_id: str | None) -> CapabilityCard | None:
        canonical = canonical_capability_id(capability_id)
        return next((item for item in self._cards if item.capability_id == canonical), None)

    def catalog_prompt(self) -> str:
        lines = [
            "第一阶段能力目录（只选择 capability_id；不要选择 action_id、工具名或子 Agent 名称）："
        ]
        for item in self._cards:
            lines.append(
                f"- {item.capability_id}: {item.description} "
                f"边界：{item.execution_boundary} 回退：{item.fallback}"
            )
        return "\n".join(lines)


__all__ = ["CapabilityCard", "CapabilityRegistry"]
