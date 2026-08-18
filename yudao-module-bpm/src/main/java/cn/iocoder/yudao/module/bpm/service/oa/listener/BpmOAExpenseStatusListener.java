package cn.iocoder.yudao.module.bpm.service.oa.listener;

import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAExpenseService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAExpenseServiceImpl;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

/**
 * OA 报销单的结果的监听器实现类
 *
 * @author 芋道源码
 */
@Component
public class BpmOAExpenseStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private BpmOAExpenseService expenseService;

    @Override
    protected String getProcessDefinitionKey() {
        return BpmOAExpenseServiceImpl.PROCESS_KEY;
    }

    @Override
    protected void onEvent(BpmProcessInstanceStatusEvent event) {
        // 如果 businessKey 为空，说明该流程实例不是通过报销功能创建的，直接返回
        if (event.getBusinessKey() == null) {
            return;
        }
        expenseService.updateExpenseStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
    }

}
