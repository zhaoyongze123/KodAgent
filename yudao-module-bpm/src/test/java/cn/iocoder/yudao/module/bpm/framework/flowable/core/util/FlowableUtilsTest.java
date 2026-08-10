package cn.iocoder.yudao.module.bpm.framework.flowable.core.util;

import org.flowable.engine.repository.ModelQuery;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

class FlowableUtilsTest {

    @Test
    void shouldUseSingleTenantByDefault() {
        assertThat(FlowableUtils.isSingleTenantMode()).isTrue();
        assertThat(FlowableUtils.getTenantId()).isEqualTo("1");
    }

    @Test
    void shouldNotFilterModelTenantInSingleTenantMode() {
        ModelQuery query = mock(ModelQuery.class);

        assertThat(FlowableUtils.applyTenantFilter(query)).isSameAs(query);
        verify(query, never()).modelTenantId(anyString());
    }

}
