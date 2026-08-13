"""主 Agent 的分阶段提示词契约。

本目录只定义模型在“规划、领域规划、执行、汇总”各阶段应遵守的通用行为，
并通过 ``PROMPT_VERSION`` 让提示词变更可以追溯。业务动作、权限、字段约束
和工具参数仍以 Action Catalog、计划编译器及工具 Schema 为唯一事实源，不能
为了方便而复制到提示词中，避免两处规则逐渐不一致。

结构导读：
* ``common``：所有阶段共享的安全边界；
* ``router``：主 Agent 的意图路由阶段；
* ``domain``：已选领域后的动作与字段规划阶段；
* ``execution``：已编译计划的执行阶段；
* ``synthesis``：基于真实工具结果生成最终答复的阶段。
"""

from .common import COMMON_PROMPT
from .domain import DOMAIN_PLANNER_PROMPT
from .execution import EXECUTION_PROMPT
from .router import INTENT_ROUTER_PROMPT
from .synthesis import SYNTHESIS_PROMPT

PROMPT_VERSION = "intent-routing-v3"

__all__ = [
    "COMMON_PROMPT",
    "DOMAIN_PLANNER_PROMPT",
    "EXECUTION_PROMPT",
    "INTENT_ROUTER_PROMPT",
    "PROMPT_VERSION",
    "SYNTHESIS_PROMPT",
]
