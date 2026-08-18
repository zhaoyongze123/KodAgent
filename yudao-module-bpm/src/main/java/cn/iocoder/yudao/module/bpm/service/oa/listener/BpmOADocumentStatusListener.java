package cn.iocoder.yudao.module.bpm.service.oa.listener;

import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOADocumentService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOADocumentServiceImpl;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

@Component
public class BpmOADocumentStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private BpmOADocumentService documentService;

    @Override
    protected String getProcessDefinitionKey() {
        return BpmOADocumentServiceImpl.PROCESS_KEY;
    }

    @Override
    protected void onEvent(BpmProcessInstanceStatusEvent event) {
        if (event.getBusinessKey() == null) {
            return;
        }
        documentService.updateDocumentStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
    }

}
