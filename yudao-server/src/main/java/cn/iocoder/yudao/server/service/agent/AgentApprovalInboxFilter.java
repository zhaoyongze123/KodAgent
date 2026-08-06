package cn.iocoder.yudao.server.service.agent;

import cn.hutool.core.util.StrUtil;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Deterministic, side-effect-free filtering for the Agent approval inbox.
 *
 * <p>The model supplies only the query criteria. This class evaluates those
 * criteria against permission-filtered BPM facts collected by the facade.
 * It deliberately has no Flowable or HTTP dependency so its rules stay
 * directly unit-testable.</p>
 */
public final class AgentApprovalInboxFilter {

    private AgentApprovalInboxFilter() {
    }

    public static List<String> exclusionReasons(Criteria criteria, Candidate candidate, LocalDateTime now) {
        List<String> reasons = new ArrayList<>();
        if (!matchesProcessType(criteria.getProcessTypes(), candidate.getProcessDefinitionName(), candidate.getProcessDefinitionKey())) {
            reasons.add("PROCESS_TYPE_MISMATCH");
        }
        if (!matchesAmount(criteria.getAmountOperator(), criteria.getAmount(), candidate.getAmount())) {
            reasons.add(candidate.getAmount() == null ? "AMOUNT_UNAVAILABLE" : "AMOUNT_MISMATCH");
        }
        if (Boolean.TRUE.equals(criteria.getAmountPresent()) && candidate.getAmount() == null
                && !reasons.contains("AMOUNT_UNAVAILABLE")) {
            reasons.add("AMOUNT_UNAVAILABLE");
        }
        if (!matchesCreatedTime(criteria.getCreatedFrom(), criteria.getCreatedTo(), candidate.getCreatedTime())) {
            reasons.add("CREATED_TIME_MISMATCH");
        }
        if (!matchesDepartment(criteria.getDepartment(), candidate.getDepartmentName())) {
            reasons.add("DEPARTMENT_MISMATCH");
        }
        if (!matchesPendingDays(criteria.getMinPendingDays(), candidate.getCreatedTime(), now)) {
            reasons.add("PENDING_DAYS_MISMATCH");
        }
        return reasons;
    }

    private static boolean matchesProcessType(List<String> expectedTypes, String name, String key) {
        if (expectedTypes == null || expectedTypes.isEmpty()) {
            return true;
        }
        return expectedTypes.stream().filter(StrUtil::isNotBlank)
                .anyMatch(expected -> containsIgnoreCase(name, expected) || containsIgnoreCase(key, expected));
    }

    private static boolean matchesAmount(String operator, BigDecimal expected, BigDecimal actual) {
        if (StrUtil.isBlank(operator) && expected == null) {
            return true;
        }
        if (expected == null || actual == null) {
            return false;
        }
        int comparison = actual.compareTo(expected);
        if ("LT".equalsIgnoreCase(operator)) return comparison < 0;
        if ("LTE".equalsIgnoreCase(operator)) return comparison <= 0;
        if ("EQ".equalsIgnoreCase(operator)) return comparison == 0;
        if ("GTE".equalsIgnoreCase(operator)) return comparison >= 0;
        if ("GT".equalsIgnoreCase(operator)) return comparison > 0;
        return false;
    }

    private static boolean matchesCreatedTime(LocalDateTime from, LocalDateTime to, LocalDateTime createdTime) {
        if (createdTime == null) {
            return from == null && to == null;
        }
        return (from == null || !createdTime.isBefore(from)) && (to == null || !createdTime.isAfter(to));
    }

    private static boolean matchesDepartment(String expected, String actual) {
        return StrUtil.isBlank(expected) || containsIgnoreCase(actual, expected);
    }

    private static boolean matchesPendingDays(Integer minimumDays, LocalDateTime createdTime, LocalDateTime now) {
        if (minimumDays == null) {
            return true;
        }
        return createdTime != null && Duration.between(createdTime, now).toDays() >= minimumDays;
    }

    private static boolean containsIgnoreCase(String value, String expected) {
        return StrUtil.isNotBlank(value) && StrUtil.isNotBlank(expected)
                && value.toLowerCase().contains(expected.trim().toLowerCase());
    }

    public static int pendingDays(LocalDateTime createdTime, LocalDateTime now) {
        return createdTime == null ? 0 : Math.max(0, (int) Duration.between(createdTime, now).toDays());
    }

    public static final class Criteria {
        private final List<String> processTypes;
        private final String amountOperator;
        private final BigDecimal amount;
        private final LocalDateTime createdFrom;
        private final LocalDateTime createdTo;
        private final String department;
        private final Integer minPendingDays;
        private final Boolean amountPresent;

        public Criteria(List<String> processTypes, String amountOperator, BigDecimal amount,
                        LocalDateTime createdFrom, LocalDateTime createdTo, String department,
                        Integer minPendingDays) {
            this(processTypes, amountOperator, amount, createdFrom, createdTo, department, minPendingDays, null);
        }

        public Criteria(List<String> processTypes, String amountOperator, BigDecimal amount,
                        LocalDateTime createdFrom, LocalDateTime createdTo, String department,
                        Integer minPendingDays, Boolean amountPresent) {
            this.processTypes = processTypes == null ? Collections.emptyList() : processTypes;
            this.amountOperator = amountOperator;
            this.amount = amount;
            this.createdFrom = createdFrom;
            this.createdTo = createdTo;
            this.department = department;
            this.minPendingDays = minPendingDays;
            this.amountPresent = amountPresent;
        }

        public List<String> getProcessTypes() { return processTypes; }
        public String getAmountOperator() { return amountOperator; }
        public BigDecimal getAmount() { return amount; }
        public LocalDateTime getCreatedFrom() { return createdFrom; }
        public LocalDateTime getCreatedTo() { return createdTo; }
        public String getDepartment() { return department; }
        public Integer getMinPendingDays() { return minPendingDays; }
        public Boolean getAmountPresent() { return amountPresent; }
    }

    public static final class Candidate {
        private final String processDefinitionName;
        private final String processDefinitionKey;
        private final BigDecimal amount;
        private final LocalDateTime createdTime;
        private final String departmentName;

        public Candidate(String processDefinitionName, String processDefinitionKey, BigDecimal amount,
                         LocalDateTime createdTime, String departmentName) {
            this.processDefinitionName = processDefinitionName;
            this.processDefinitionKey = processDefinitionKey;
            this.amount = amount;
            this.createdTime = createdTime;
            this.departmentName = departmentName;
        }

        public String getProcessDefinitionName() { return processDefinitionName; }
        public String getProcessDefinitionKey() { return processDefinitionKey; }
        public BigDecimal getAmount() { return amount; }
        public LocalDateTime getCreatedTime() { return createdTime; }
        public String getDepartmentName() { return departmentName; }
    }
}
