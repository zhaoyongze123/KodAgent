package cn.iocoder.yudao.module.bpm.service.message;

import cn.iocoder.yudao.framework.common.exception.ServiceException;
import cn.iocoder.yudao.framework.common.enums.UserTypeEnum;
import cn.iocoder.yudao.framework.websocket.core.sender.WebSocketMessageSender;
import cn.iocoder.yudao.framework.web.config.WebProperties;
import cn.iocoder.yudao.module.bpm.convert.message.BpmMessageConvert;
import cn.iocoder.yudao.module.bpm.framework.notify.BpmNotifyTemplateInitRunner;
import cn.iocoder.yudao.module.infra.api.websocket.WebSocketSenderApi;
import cn.iocoder.yudao.module.bpm.enums.message.BpmMessageEnum;
import cn.iocoder.yudao.module.bpm.service.message.dto.BpmMessageSendWhenProcessInstanceApproveReqDTO;
import cn.iocoder.yudao.module.bpm.service.message.dto.BpmMessageSendWhenProcessInstanceRejectReqDTO;
import cn.iocoder.yudao.module.bpm.service.message.dto.BpmMessageSendWhenTaskCreatedReqDTO;
import cn.iocoder.yudao.module.bpm.service.message.dto.BpmMessageSendWhenTaskTimeoutReqDTO;
import cn.iocoder.yudao.module.bpm.service.message.dto.BpmTaskAssignedWebSocketMessage;
import cn.iocoder.yudao.module.system.controller.admin.notify.vo.message.NotifyMessageRespVO;
import cn.iocoder.yudao.module.system.dal.dataobject.notify.NotifyTemplateDO;
import cn.iocoder.yudao.module.system.service.notify.NotifyMessageService;
import cn.iocoder.yudao.module.system.service.notify.NotifyTemplateService;
import cn.iocoder.yudao.module.system.api.sms.SmsSendApi;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.util.HashMap;
import java.util.Map;

import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.SMS_SEND_MOBILE_NOT_EXISTS;

/**
 * BPM 消息 Service 实现类
 *
 * @author 芋道源码
 */
@Service
@Validated
@Slf4j
public class BpmMessageServiceImpl implements BpmMessageService {

    private static final String TASK_ASSIGNED_NOTIFY_TEMPLATE_CODE = BpmMessageEnum.TASK_ASSIGNED.getSmsTemplateCode();

    @Resource
    private SmsSendApi smsSendApi;

    @Resource
    private NotifyTemplateService notifyTemplateService;

    @Resource
    private NotifyMessageService notifyMessageService;

    @Resource
    private WebProperties webProperties;

    @Resource
    private WebSocketSenderApi webSocketSenderApi;

    @SuppressWarnings("SpringJavaAutowiredFieldsWarningInspection")
    @Autowired(required = false) // 允许通过 yudao.websocket.enable=false 关闭实时推送
    private WebSocketMessageSender webSocketMessageSender;

    @Override
    public void sendMessageWhenProcessInstanceApprove(BpmMessageSendWhenProcessInstanceApproveReqDTO reqDTO) {
        Map<String, Object> templateParams = new HashMap<>();
        templateParams.put("processInstanceName", reqDTO.getProcessInstanceName());
        templateParams.put("detailUrl", getProcessInstanceDetailUrl(reqDTO.getProcessInstanceId()));
        sendSmsToAdminSafely(reqDTO.getStartUserId(),
                BpmMessageEnum.PROCESS_INSTANCE_APPROVE.getSmsTemplateCode(), templateParams, "审批通过");
        sendNotifyToAdminSafely(reqDTO.getStartUserId(),
                BpmNotifyTemplateInitRunner.PROCESS_INSTANCE_APPROVE_NOTIFY_TEMPLATE_CODE,
                templateParams, "审批通过");
    }

    @Override
    public void sendMessageWhenProcessInstanceReject(BpmMessageSendWhenProcessInstanceRejectReqDTO reqDTO) {
        Map<String, Object> templateParams = new HashMap<>();
        templateParams.put("processInstanceName", reqDTO.getProcessInstanceName());
        templateParams.put("reason", reqDTO.getReason());
        templateParams.put("detailUrl", getProcessInstanceDetailUrl(reqDTO.getProcessInstanceId()));
        sendSmsToAdminSafely(reqDTO.getStartUserId(),
                BpmMessageEnum.PROCESS_INSTANCE_REJECT.getSmsTemplateCode(), templateParams, "审批拒绝");
        sendNotifyToAdminSafely(reqDTO.getStartUserId(),
                BpmNotifyTemplateInitRunner.PROCESS_INSTANCE_REJECT_NOTIFY_TEMPLATE_CODE,
                templateParams, "审批拒绝");
    }

    @Override
    public void sendMessageWhenTaskAssigned(BpmMessageSendWhenTaskCreatedReqDTO reqDTO) {
        Map<String, Object> templateParams = new HashMap<>();
        templateParams.put("processInstanceName", reqDTO.getProcessInstanceName());
        templateParams.put("taskName", reqDTO.getTaskName());
        templateParams.put("startUserNickname", reqDTO.getStartUserNickname());
        templateParams.put("detailUrl", getProcessInstanceDetailUrl(reqDTO.getProcessInstanceId()));
        sendSmsToAdminSafely(reqDTO.getAssigneeUserId(),
                BpmMessageEnum.TASK_ASSIGNED.getSmsTemplateCode(), templateParams, "任务分配");
        sendTaskAssignedNotifyMessage(reqDTO, templateParams);
        if (webSocketMessageSender != null) {
            webSocketMessageSender.sendObject(UserTypeEnum.ADMIN.getValue(), reqDTO.getAssigneeUserId(),
                    "task-assigned", buildTaskAssignedWebSocketMessage(reqDTO));
        }
    }

    @Override
    public void sendMessageWhenTaskTimeout(BpmMessageSendWhenTaskTimeoutReqDTO reqDTO) {
        Map<String, Object> templateParams = new HashMap<>();
        templateParams.put("processInstanceName", reqDTO.getProcessInstanceName());
        templateParams.put("taskName", reqDTO.getTaskName());
        templateParams.put("detailUrl", getProcessInstanceDetailUrl(reqDTO.getProcessInstanceId()));
        sendSmsToAdminSafely(reqDTO.getAssigneeUserId(),
                BpmMessageEnum.TASK_TIMEOUT.getSmsTemplateCode(), templateParams, "任务超时");
    }

    private String getProcessInstanceDetailUrl(String taskId) {
        return webProperties.getAdminUi().getUrl() + "/bpm/process-instance/detail?id=" + taskId;
    }

    private void sendSmsToAdminSafely(Long userId, String templateCode, Map<String, Object> templateParams,
                                      String scene) {
        try {
            smsSendApi.sendSingleSmsToAdmin(BpmMessageConvert.INSTANCE.convert(userId, templateCode, templateParams));
        } catch (ServiceException ex) {
            if (SMS_SEND_MOBILE_NOT_EXISTS.getCode().equals(ex.getCode())) {
                log.warn("[sendSmsToAdminSafely][{} 短信跳过，userId={}，原因：{}]", scene, userId, ex.getMessage());
                return;
            }
            throw ex;
        }
    }

    private void sendNotifyToAdminSafely(Long userId, String templateCode, Map<String, Object> templateParams,
                                         String scene) {
        try {
            NotifyTemplateDO template = notifyTemplateService.getNotifyTemplateByCodeFromCache(templateCode);
            if (template == null) {
                log.warn("[sendNotifyToAdminSafely][{} 站内信模板缺失，userId={}，templateCode={}]",
                        scene, userId, templateCode);
                return;
            }
            String content = notifyTemplateService.formatNotifyTemplateContent(template.getContent(), templateParams);
            Long messageId = notifyMessageService.createNotifyMessage(userId,
                    UserTypeEnum.ADMIN.getValue(), template, content, templateParams);
            webSocketSenderApi.sendObject(UserTypeEnum.ADMIN.getValue(), userId, "notice-push",
                    buildNotifyPushMessage(messageId, template, content));
        } catch (Exception ex) {
            log.error("[sendNotifyToAdminSafely][{} 站内信发送失败，userId={}]", scene, userId, ex);
        }
    }

    private NotifyMessageRespVO buildNotifyPushMessage(Long messageId, NotifyTemplateDO template, String content) {
        NotifyMessageRespVO message = new NotifyMessageRespVO();
        message.setId(messageId);
        message.setTemplateId(template.getId());
        message.setTemplateCode(template.getCode());
        message.setTemplateNickname(template.getNickname());
        message.setTemplateContent(content);
        message.setTemplateType(template.getType());
        message.setCreateTime(java.time.LocalDateTime.now());
        return message;
    }

    private void sendTaskAssignedNotifyMessage(BpmMessageSendWhenTaskCreatedReqDTO reqDTO,
                                               Map<String, Object> templateParams) {
        Map<String, Object> notifyContentParams = new HashMap<>(templateParams);
        notifyContentParams.put("processInstanceId", reqDTO.getProcessInstanceId());
        notifyContentParams.put("taskId", reqDTO.getTaskId());
        Map<String, Object> notifyPersistParams = new HashMap<>();
        notifyPersistParams.put("processInstanceId", reqDTO.getProcessInstanceId());
        notifyPersistParams.put("taskId", reqDTO.getTaskId());
        try {
            NotifyTemplateDO template = notifyTemplateService.getNotifyTemplateByCodeFromCache(
                    TASK_ASSIGNED_NOTIFY_TEMPLATE_CODE);
            if (template == null) {
                log.error("[sendTaskAssignedNotifyMessage][流程任务({}) 的站内信模板({})不存在]",
                        reqDTO.getTaskId(), TASK_ASSIGNED_NOTIFY_TEMPLATE_CODE);
                return;
            }
            String content = notifyTemplateService.formatNotifyTemplateContent(
                    template.getContent(), notifyContentParams);
            notifyMessageService.createNotifyMessage(reqDTO.getAssigneeUserId(),
                    UserTypeEnum.ADMIN.getValue(), template, content, notifyPersistParams);
        } catch (Exception ex) {
            log.error("[sendTaskAssignedNotifyMessage][流程任务({}) 发送站内信失败]", reqDTO.getTaskId(), ex);
        }
    }

    private BpmTaskAssignedWebSocketMessage buildTaskAssignedWebSocketMessage(BpmMessageSendWhenTaskCreatedReqDTO reqDTO) {
        BpmTaskAssignedWebSocketMessage message = new BpmTaskAssignedWebSocketMessage();
        message.setProcessInstanceId(reqDTO.getProcessInstanceId());
        message.setProcessInstanceName(reqDTO.getProcessInstanceName());
        message.setTaskId(reqDTO.getTaskId());
        message.setTaskName(reqDTO.getTaskName());
        message.setStartUserId(reqDTO.getStartUserId());
        message.setStartUserNickname(reqDTO.getStartUserNickname());
        message.setAssigneeUserId(reqDTO.getAssigneeUserId());
        return message;
    }

}
