"""通用附件交付信号。

这里仅判断用户是否明确要求一个可下载文件，以及是否明确指定文件格式。
它不识别周报、分析报告等业务类型，也不决定文件内容；业务事实和正文仍由
模型/领域工具提供，Java 只负责受控渲染和存储。
"""

from __future__ import annotations

import re
from typing import Literal


ArtifactFormat = Literal["DOCX", "XLSX"]

_FILE_REQUEST = re.compile(
    r"(?:导出|下载|附件|文件|文档|保存(?:成|为)?|给我一份|发我一份|生成一份.*(?:word|excel|文档|文件))",
    re.IGNORECASE,
)
_DOCX = re.compile(r"(?:docx|word|word文档|文档版)", re.IGNORECASE)
_XLSX = re.compile(r"(?:xlsx|excel|工作簿|电子表格)", re.IGNORECASE)
_NEGATED = re.compile(r"(?:不要|不需要|无需|无须|不用|不必|别|勿)\s*(?:再\s*)?(?:生成|导出|下载|创建|制作)?\s*(?:附件|文件|文档|word|excel|xlsx|docx)?", re.IGNORECASE)


def artifact_requested(message: str) -> bool:
    """判断是否有明确的持久文件交付意图。"""

    text = str(message or "").strip()
    if not text or _NEGATED.search(text):
        return False
    return bool(_FILE_REQUEST.search(text) or _DOCX.search(text) or _XLSX.search(text))


def requested_formats(message: str) -> tuple[ArtifactFormat, ...]:
    """返回用户明确指定的格式；未指定时不替用户增加第二种格式。"""

    if not artifact_requested(message):
        return ()
    text = str(message or "")
    formats: list[ArtifactFormat] = []
    if _DOCX.search(text):
        formats.append("DOCX")
    if _XLSX.search(text):
        formats.append("XLSX")
    return tuple(formats or ("DOCX",))


__all__ = ["ArtifactFormat", "artifact_requested", "requested_formats"]
