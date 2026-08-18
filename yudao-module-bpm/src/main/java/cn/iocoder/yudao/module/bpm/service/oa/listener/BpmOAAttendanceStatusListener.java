package cn.iocoder.yudao.module.bpm.service.oa.listener;

import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.iocoder.yudao.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAAttendanceService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAAttendanceServiceImpl;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

/**
 * OA 补卡单的结果的监听器实现类
 *
 * @author 芋道源码
 */
@Component
public class BpmOAAttendanceStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private BpmOAAttendanceService attendanceService;

    @Override
    protected String getProcessDefinitionKey() {
        return BpmOAAttendanceServiceImpl.PROCESS_KEY;
    }

    @Override
    protected void onEvent(BpmProcessInstanceStatusEvent event) {
        // 如果 businessKey 为空，说明该流程实例不是通过补卡功能创建的，直接返回
        if (event.getBusinessKey() == null) {
            return;
        }
        attendanceService.updateAttendanceStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
    }

}
