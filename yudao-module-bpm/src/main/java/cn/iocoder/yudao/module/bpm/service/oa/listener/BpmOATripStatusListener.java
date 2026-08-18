package cn.iocoder.yudao.module.bpm.service.oa.listener;

import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOATripService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOATripServiceImpl;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

/**
 * OA 出差单的结果的监听器实现类
 *
 * @author 芋道源码
 */
@Component
public class BpmOATripStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private BpmOATripService tripService;

    @Override
    protected String getProcessDefinitionKey() {
        return BpmOATripServiceImpl.PROCESS_KEY;
    }

    @Override
    protected void onEvent(BpmProcessInstanceStatusEvent event) {
        // 如果 businessKey 为空，说明该流程实例不是通过出差功能创建的，直接返回
        if (event.getBusinessKey() == null) {
            return;
        }
        tripService.updateTripStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
    }

}
