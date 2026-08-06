from src.oa_agent import system_prompt


def test_parent_synthesis_contract_requires_added_presentation_value():
    prompt = system_prompt()

    assert "不能把子 Agent 的 output 原样逐字复制" in prompt
    assert "列表或表格超过 5 条时" in prompt
    assert "前 5 条代表性记录" in prompt
    assert "用户明确要求“全部/完整/明细”时" in prompt
    assert "不得为了制造文本差异" in prompt


def test_parent_synthesis_contract_preserves_safety_critical_facts():
    prompt = system_prompt()

    assert "审批、预约确认、权限拒绝和业务错误等安全关键结果必须完整保留" in prompt
    assert "不得虚构后续操作" in prompt
