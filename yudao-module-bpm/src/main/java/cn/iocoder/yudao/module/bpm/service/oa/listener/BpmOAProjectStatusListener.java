package cn.iocoder.yudao.module.bpm.service.oa.listener;

import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAProjectService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAProjectServiceImpl;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

@Component
public class BpmOAProjectStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private BpmOAProjectService projectService;

    @Override
    protected String getProcessDefinitionKey() {
        return BpmOAProjectServiceImpl.PROCESS_KEY;
    }

    @Override
    protected void onEvent(BpmProcessInstanceStatusEvent event) {
        if (event.getBusinessKey() == null) {
            return;
        }
        projectService.updateProjectStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
    }

}
