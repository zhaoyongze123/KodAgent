import src.oa_agent as oa_agent


def test_main_agent_presents_child_results_without_copying_or_losing_facts():
    prompt = oa_agent.system_prompt()

    assert "不能把子 Agent 的 output 原样逐字复制" in prompt
    assert "事实不变的提炼、重排、分组或格式化" in prompt
    assert "总数、关键结论和前几条代表性记录" in prompt
    assert "用户明确要求“全部/完整/明细”时，必须完整呈现" in prompt
    assert "不得擅自截断、遗漏或概括关键事实" in prompt
    assert "没有真实依据时不要添加追问、建议或新事实" in prompt
