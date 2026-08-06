"""Small, provider-neutral contracts for domain plan compilation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ...domain.plan import CompiledTaskPlan


@dataclass(frozen=True)
class CompileContext:
    """Validated input shared by a domain compiler.

    ``payload`` and ``query_intent`` are already transport-normalized by the
    common action boundary.  Domain compilers may canonicalize values, but may
    not infer a domain from user prose or perform side effects.
    """

    capability_id: str
    execution_class: str
    payload: dict[str, Any] = field(default_factory=dict)
    query_intent: dict[str, Any] | None = None
    action_id: str | None = None


class DomainPlanCompiler(Protocol):
    capability_id: str

    def compile(self, context: CompileContext) -> CompiledTaskPlan | None:
        """Return a plan for the domain or ``None`` when the class is foreign."""


class PlanCompilerRegistry:
    """Deterministic registry for domain compilers.

    Registration is keyed by capability, not by user-facing keywords.  A
    duplicate registration is a startup error so adding a new domain cannot
    silently shadow an existing compiler.
    """

    def __init__(self, compilers: tuple[DomainPlanCompiler, ...] = ()) -> None:
        self._compilers: dict[str, DomainPlanCompiler] = {}
        for compiler in compilers:
            self.register(compiler)

    def register(self, compiler: DomainPlanCompiler, *, replace: bool = False) -> None:
        capability = str(compiler.capability_id or "").strip()
        if not capability:
            raise ValueError("领域编译器必须声明 capability_id")
        if capability in self._compilers and not replace:
            raise ValueError(f"领域编译器重复注册: {capability}")
        self._compilers[capability] = compiler

    def get(self, capability_id: str) -> DomainPlanCompiler | None:
        return self._compilers.get(str(capability_id or "").strip())

    def compile(self, context: CompileContext) -> CompiledTaskPlan | None:
        compiler = self.get(context.capability_id)
        return compiler.compile(context) if compiler else None

    def capabilities(self) -> tuple[str, ...]:
        return tuple(self._compilers)


__all__ = ["CompileContext", "DomainPlanCompiler", "PlanCompilerRegistry"]
