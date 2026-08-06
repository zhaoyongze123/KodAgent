"""LangGraph Server 入口。

这一层只负责把现有 DeepAgent 暴露成 agent-chat-ui 能理解的 Graph，
不在这里重复实现 OA 业务规则；认证和多租户 Gateway 在下一阶段接入。
"""

try:
    # LangGraph CLI loads this file by path, so it is not always imported as
    # part of the ``src`` package.  The absolute import works from the project
    # root, while the fallback keeps direct module execution/imports working.
    from src.oa_agent import build_agent
except ModuleNotFoundError as exc:
    if exc.name != "src":
        raise
    from oa_agent import build_agent


# LangGraph Server owns persistence/checkpoints.  The console entrypoint keeps
# using build_agent() with the project's configured saver.
graph = build_agent(use_checkpointer=False)
