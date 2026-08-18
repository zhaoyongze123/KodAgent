package cn.iocoder.yudao.module.bpm.service.oa.listener;

import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAOutingService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAOutingServiceImpl;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

@Component
public class BpmOAOutingStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private BpmOAOutingService outingService;

    @Override
    protected String getProcessDefinitionKey() {
        return BpmOAOutingServiceImpl.PROCESS_KEY;
    }

    @Override
    protected void onEvent(BpmProcessInstanceStatusEvent event) {
        if (event.getBusinessKey() == null) {
            return;
        }
        outingService.updateOutingStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
    }

}
