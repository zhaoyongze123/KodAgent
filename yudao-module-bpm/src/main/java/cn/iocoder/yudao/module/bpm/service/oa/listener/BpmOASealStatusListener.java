package cn.iocoder.yudao.module.bpm.service.oa.listener;

import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOASealService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOASealServiceImpl;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

/**
 * OA 用章单的结果的监听器实现类
 *
 * @author 芋道源码
 */
@Component
public class BpmOASealStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private BpmOASealService sealService;

    @Override
    protected String getProcessDefinitionKey() {
        return BpmOASealServiceImpl.PROCESS_KEY;
    }

    @Override
    protected void onEvent(BpmProcessInstanceStatusEvent event) {
        // 如果 businessKey 为空，说明该流程实例不是通过用章功能创建的，直接返回
        if (event.getBusinessKey() == null) {
            return;
        }
        sealService.updateSealStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
    }

}
