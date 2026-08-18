package cn.iocoder.yudao.module.bpm.service.task;

import org.junit.jupiter.api.Test;
import org.flowable.engine.HistoryService;
import org.flowable.engine.history.HistoricProcessInstance;
import org.flowable.engine.history.HistoricProcessInstanceQuery;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Arrays;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class BpmTaskServiceImplTest {

    @Test
    void normalizesNumericFormTypeForProcessVariableQueries() {
        assertThat(BpmTaskServiceImpl.normalizeFormTypeFilter("2")).isEqualTo(2);
        assertThat(BpmTaskServiceImpl.normalizeFormTypeFilter("2.5")).isEqualTo(2.5D);
    }

    @Test
    void keepsTextFormTypeForProcessVariableQueries() {
        assertThat(BpmTaskServiceImpl.normalizeFormTypeFilter("business-trip")).isEqualTo("business-trip");
    }

    @Test
    void findsTaskProcessIdsByProcessInstanceName() {
        HistoryService historyService = mock(HistoryService.class);
        HistoricProcessInstanceQuery query = mock(HistoricProcessInstanceQuery.class);
        HistoricProcessInstance firstInstance = mock(HistoricProcessInstance.class);
        HistoricProcessInstance secondInstance = mock(HistoricProcessInstance.class);
        when(historyService.createHistoricProcessInstanceQuery()).thenReturn(query);
        when(query.processInstanceNameLike("%报销%")).thenReturn(query);
        when(query.list()).thenReturn(Arrays.asList(firstInstance, secondInstance));
        when(firstInstance.getId()).thenReturn("expense-1");
        when(secondInstance.getId()).thenReturn("expense-2");

        BpmTaskServiceImpl service = new BpmTaskServiceImpl();
        ReflectionTestUtils.setField(service, "historyService", historyService);

        assertThat(service.findProcessInstanceIdsByName("报销"))
                .containsExactlyInAnyOrder("expense-1", "expense-2");
    }

}
