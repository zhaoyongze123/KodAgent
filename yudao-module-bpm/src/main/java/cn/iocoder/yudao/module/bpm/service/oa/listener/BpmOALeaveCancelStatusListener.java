package cn.iocoder.yudao.module.bpm.service.oa.listener;

import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOALeaveCancelService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOALeaveCancelServiceImpl;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

@Component
public class BpmOALeaveCancelStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private BpmOALeaveCancelService leaveCancelService;

    @Override
    protected String getProcessDefinitionKey() {
        return BpmOALeaveCancelServiceImpl.PROCESS_KEY;
    }

    @Override
    protected void onEvent(BpmProcessInstanceStatusEvent event) {
        if (event.getBusinessKey() == null) {
            return;
        }
        leaveCancelService.updateLeaveCancelStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
    }

}
