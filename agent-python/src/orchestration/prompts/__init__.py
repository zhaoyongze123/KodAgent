"""Small, versioned prompt contracts for the parent orchestration graph.

Prompt modules describe model responsibilities.  Business facts stay in the
Action Catalog, compiler and tool schemas; they are intentionally not copied
into these strings.
"""

from .common import COMMON_PROMPT
from .domain import DOMAIN_PLANNER_PROMPT
from .execution import EXECUTION_PROMPT
from .router import INTENT_ROUTER_PROMPT
from .synthesis import SYNTHESIS_PROMPT

PROMPT_VERSION = "intent-routing-v1"

__all__ = [
    "COMMON_PROMPT",
    "DOMAIN_PLANNER_PROMPT",
    "EXECUTION_PROMPT",
    "INTENT_ROUTER_PROMPT",
    "PROMPT_VERSION",
    "SYNTHESIS_PROMPT",
]
