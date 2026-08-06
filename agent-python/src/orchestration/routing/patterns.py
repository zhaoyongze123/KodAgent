"""Pure message patterns used by bounded route-recovery handlers.

These expressions are safety guards for already typed or state-bound requests;
they are not the primary business-domain classifier.  Keeping them separate
from the route facade prevents the router from becoming a second business
workflow implementation.
"""

from __future__ import annotations

import re


DATE_QUERY = re.compile(
    r"(?P<year>20\d{2})\s*(?:年|-|/|\.)\s*(?P<month>\d{1,2})\s*(?:月|-|/|\.)\s*(?P<day>\d{1,2})\s*日?"
)
MEETING_UPDATE_FOLLOW_UP = re.compile(r"修改|更改|改(?:为|到|成|一下|期)|换(?:到|成)|调整|变更|改时间|延后|提前|推迟|重排")
MEETING_CANCEL_FOLLOW_UP = re.compile(r"取消|删除|撤销")
BOOKING_ID_IN_MESSAGE = re.compile(r"(?:预约(?:编号|号)?|booking(?:\s*id)?|会议)\s*[#：:#-]?\s*(\d+)", re.I)
MEETING_ORDINAL = re.compile(r"第\s*(\d+)\s*(?:条|个|场|项)?")
SCHEDULE_UPDATE_FOLLOW_UP = re.compile(r"修改|更改|改(?:为|到|成|一下|期)|换(?:到|成)|调整|变更|改时间|延后|提前|推迟|重排")
SCHEDULE_CANCEL_FOLLOW_UP = re.compile(r"取消|删除|撤销")
SCHEDULE_ID_IN_MESSAGE = re.compile(r"(?:日程(?:编号|号)?|schedule(?:\s*id)?)\s*[#：:#-]?\s*(\d+)", re.I)
SCHEDULE_ORDINAL = re.compile(r"第\s*(\d+)\s*(?:条|个|项|个日程)?")
PARTY_FILE_ATTACHMENT_QUERY = re.compile(
    r"附件|附件信息|可发送的附件|包含附件|有没有附件|查看附件|核对附件|预览附件|下载附件|发送附件|附件发给我|把附件发给我",
)
PARTY_FILE_EXPLICIT_WRITE = re.compile(
    r"起草|创建|新建|拟定|编写|发布(?:新|一份|一个)?|正式发布|修改|更新|编辑|变更|调整|删除|撤销|作废",
)


__all__ = [
    "BOOKING_ID_IN_MESSAGE",
    "DATE_QUERY",
    "MEETING_CANCEL_FOLLOW_UP",
    "MEETING_ORDINAL",
    "MEETING_UPDATE_FOLLOW_UP",
    "PARTY_FILE_ATTACHMENT_QUERY",
    "PARTY_FILE_EXPLICIT_WRITE",
    "SCHEDULE_CANCEL_FOLLOW_UP",
    "SCHEDULE_ID_IN_MESSAGE",
    "SCHEDULE_ORDINAL",
    "SCHEDULE_UPDATE_FOLLOW_UP",
]
