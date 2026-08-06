package cn.iocoder.yudao.server.service.agent;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.Collections;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AgentApprovalInboxFilterTest {

    private static final LocalDateTime NOW = LocalDateTime.of(2026, 7, 30, 12, 0);

    @Test
    void acceptsCandidateOnlyWhenEveryStructuredCriterionMatches() {
        AgentApprovalInboxFilter.Criteria criteria = new AgentApprovalInboxFilter.Criteria(
                Collections.singletonList("报销"), "LTE", new BigDecimal("5000"),
                LocalDateTime.of(2026, 7, 1, 0, 0), null, "研发部", 2);
        AgentApprovalInboxFilter.Candidate candidate = new AgentApprovalInboxFilter.Candidate(
                "报销审批", "expense", new BigDecimal("4999.50"),
                LocalDateTime.of(2026, 7, 27, 9, 0), "研发部");

        assertTrue(AgentApprovalInboxFilter.exclusionReasons(criteria, candidate, NOW).isEmpty());
    }

    @Test
    void reportsConcreteReasonsRatherThanSilentlyDroppingCandidates() {
        AgentApprovalInboxFilter.Criteria criteria = new AgentApprovalInboxFilter.Criteria(
                Collections.singletonList("合同"), "GT", new BigDecimal("100000"),
                null, null, "法务部", 2);
        AgentApprovalInboxFilter.Candidate candidate = new AgentApprovalInboxFilter.Candidate(
                "报销审批", "expense", null, LocalDateTime.of(2026, 7, 29, 9, 0), "研发部");

        assertEquals(Arrays.asList("PROCESS_TYPE_MISMATCH", "AMOUNT_UNAVAILABLE",
                        "DEPARTMENT_MISMATCH", "PENDING_DAYS_MISMATCH"),
                AgentApprovalInboxFilter.exclusionReasons(criteria, candidate, NOW));
    }

    @Test
    void amountPresentExcludesNullAmountWithoutChangingOtherCriteria() {
        AgentApprovalInboxFilter.Criteria criteria = new AgentApprovalInboxFilter.Criteria(
                Collections.emptyList(), null, null, null, null, null, null, true);
        AgentApprovalInboxFilter.Candidate candidate = new AgentApprovalInboxFilter.Candidate(
                "报销审批", "expense", null, NOW.minusDays(1), "研发部");

        assertEquals(Collections.singletonList("AMOUNT_UNAVAILABLE"),
                AgentApprovalInboxFilter.exclusionReasons(criteria, candidate, NOW));
    }
}
