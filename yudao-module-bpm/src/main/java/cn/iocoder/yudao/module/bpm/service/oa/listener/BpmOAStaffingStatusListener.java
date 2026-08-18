package cn.iocoder.yudao.module.bpm.service.oa.listener;

import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAStaffingService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAStaffingServiceImpl;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

@Component
public class BpmOAStaffingStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private BpmOAStaffingService staffingService;

    @Override
    protected String getProcessDefinitionKey() {
        return BpmOAStaffingServiceImpl.PROCESS_KEY;
    }

    @Override
    protected void onEvent(BpmProcessInstanceStatusEvent event) {
        if (event.getBusinessKey() == null) {
            return;
        }
        staffingService.updateStaffingStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
    }

}
