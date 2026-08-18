package cn.iocoder.yudao.module.bpm.framework.notify;

import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.module.bpm.enums.message.BpmMessageEnum;
import cn.iocoder.yudao.module.system.controller.admin.notify.vo.template.NotifyTemplateSaveReqVO;
import cn.iocoder.yudao.module.system.enums.notify.NotifyTemplateTypeEnum;
import cn.iocoder.yudao.module.system.service.notify.NotifyTemplateService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

/**
 * BPM 站内信模板初始化。
 *
 * <p>审批待办通知需要持久化到 system_notify_message，这里在启动时幂等补齐模板，
 * 避免本地环境或新环境忘记手工创建模板导致消息发送失败。</p>
 */
@Component
@Slf4j
public class BpmNotifyTemplateInitRunner implements ApplicationRunner {

    private static final String TASK_ASSIGNED_NOTIFY_TEMPLATE_CODE = BpmMessageEnum.TASK_ASSIGNED.getSmsTemplateCode();
    public static final String PROCESS_INSTANCE_APPROVE_NOTIFY_TEMPLATE_CODE =
            BpmMessageEnum.PROCESS_INSTANCE_APPROVE.getSmsTemplateCode();
    public static final String PROCESS_INSTANCE_REJECT_NOTIFY_TEMPLATE_CODE =
            BpmMessageEnum.PROCESS_INSTANCE_REJECT.getSmsTemplateCode();

    @Resource
    private NotifyTemplateService notifyTemplateService;

    @Override
    public void run(ApplicationArguments args) {
        initTemplate(TASK_ASSIGNED_NOTIFY_TEMPLATE_CODE, "【工作流】任务被分配",
                "您收到了一条新的待办任务：{processInstanceName}-{taskName}，申请人：{startUserNickname}",
                "BPM 待办分配通知模板，供 oa-lite 与管理后台共用");
        initTemplate(PROCESS_INSTANCE_APPROVE_NOTIFY_TEMPLATE_CODE, "【工作流】流程已通过",
                "你发起的流程【{processInstanceName}】已审批通过，点击查看：{detailUrl}",
                "BPM 流程审批通过通知模板，供 oa-lite 与管理后台共用");
        initTemplate(PROCESS_INSTANCE_REJECT_NOTIFY_TEMPLATE_CODE, "【工作流】流程被驳回",
                "你发起的流程【{processInstanceName}】已被驳回，原因：{reason}，点击查看：{detailUrl}",
                "BPM 流程驳回通知模板，供 oa-lite 与管理后台共用");
    }

    private void initTemplate(String code, String name, String content, String remark) {
        if (notifyTemplateService.getNotifyTemplateByCodeFromCache(code) != null) {
            return;
        }
        NotifyTemplateSaveReqVO createReqVO = new NotifyTemplateSaveReqVO();
        createReqVO.setName(name);
        createReqVO.setCode(code);
        createReqVO.setType(NotifyTemplateTypeEnum.SYSTEM_MESSAGE.getType());
        createReqVO.setNickname("审批中心");
        createReqVO.setContent(content);
        createReqVO.setStatus(CommonStatusEnum.ENABLE.getStatus());
        createReqVO.setRemark(remark);
        Long templateId = notifyTemplateService.createNotifyTemplate(createReqVO);
        log.info("[initTemplate][已自动初始化 BPM 站内信模板，templateId={} code={}]", templateId, code);
    }
}
