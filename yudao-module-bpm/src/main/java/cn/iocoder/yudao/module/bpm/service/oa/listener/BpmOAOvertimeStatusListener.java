package cn.iocoder.yudao.module.bpm.service.oa.listener;

import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAOvertimeService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAOvertimeServiceImpl;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

/**
 * OA 加班单的结果的监听器实现类
 *
 * @author 芋道源码
 */
@Component
public class BpmOAOvertimeStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private BpmOAOvertimeService overtimeService;

    @Override
    protected String getProcessDefinitionKey() {
        return BpmOAOvertimeServiceImpl.PROCESS_KEY;
    }

    @Override
    protected void onEvent(BpmProcessInstanceStatusEvent event) {
        // 如果 businessKey 为空，说明该流程实例不是通过加班功能创建的，直接返回
        if (event.getBusinessKey() == null) {
            return;
        }
        overtimeService.updateOvertimeStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
    }

}
