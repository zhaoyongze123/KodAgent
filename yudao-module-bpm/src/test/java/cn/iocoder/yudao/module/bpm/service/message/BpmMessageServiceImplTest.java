package cn.iocoder.yudao.module.bpm.service.message;

import cn.iocoder.yudao.framework.common.exception.ServiceException;
import cn.iocoder.yudao.framework.web.config.WebProperties;
import cn.iocoder.yudao.module.bpm.framework.notify.BpmNotifyTemplateInitRunner;
import cn.iocoder.yudao.module.bpm.service.message.dto.BpmMessageSendWhenProcessInstanceApproveReqDTO;
import cn.iocoder.yudao.module.bpm.service.message.dto.BpmMessageSendWhenProcessInstanceRejectReqDTO;
import cn.iocoder.yudao.module.infra.api.websocket.WebSocketSenderApi;
import cn.iocoder.yudao.module.system.dal.dataobject.notify.NotifyTemplateDO;
import cn.iocoder.yudao.module.system.api.sms.SmsSendApi;
import cn.iocoder.yudao.module.system.service.notify.NotifyMessageService;
import cn.iocoder.yudao.module.system.service.notify.NotifyTemplateService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;

import javax.annotation.Resource;

import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.SMS_SEND_MOBILE_NOT_EXISTS;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;

@Import(BpmMessageServiceImpl.class)
public class BpmMessageServiceImplTest extends cn.iocoder.yudao.framework.test.core.ut.BaseDbUnitTest {

    @Resource
    private BpmMessageServiceImpl bpmMessageService;

    @MockBean
    private SmsSendApi smsSendApi;
    @MockBean
    private NotifyTemplateService notifyTemplateService;
    @MockBean
    private NotifyMessageService notifyMessageService;
    @MockBean
    private WebProperties webProperties;
    @MockBean
    private WebSocketSenderApi webSocketSenderApi;

    @BeforeEach
    public void setUp() {
        WebProperties.Ui adminUi = new WebProperties.Ui();
        adminUi.setUrl("http://127.0.0.1:5666");
        org.mockito.Mockito.when(webProperties.getAdminUi()).thenReturn(adminUi);

        when(notifyTemplateService.getNotifyTemplateByCodeFromCache(
                eq(BpmNotifyTemplateInitRunner.PROCESS_INSTANCE_APPROVE_NOTIFY_TEMPLATE_CODE)))
                .thenReturn(new NotifyTemplateDO()
                        .setId(101L)
                        .setCode(BpmNotifyTemplateInitRunner.PROCESS_INSTANCE_APPROVE_NOTIFY_TEMPLATE_CODE)
                        .setType(2)
                        .setNickname("审批中心")
                        .setContent("你发起的流程【{processInstanceName}】已审批通过，点击查看：{detailUrl}"));
        when(notifyTemplateService.getNotifyTemplateByCodeFromCache(
                eq(BpmNotifyTemplateInitRunner.PROCESS_INSTANCE_REJECT_NOTIFY_TEMPLATE_CODE)))
                .thenReturn(new NotifyTemplateDO()
                        .setId(102L)
                        .setCode(BpmNotifyTemplateInitRunner.PROCESS_INSTANCE_REJECT_NOTIFY_TEMPLATE_CODE)
                        .setType(2)
                        .setNickname("审批中心")
                        .setContent("你发起的流程【{processInstanceName}】已被驳回，原因：{reason}，点击查看：{detailUrl}"));
        when(notifyTemplateService.formatNotifyTemplateContent(any(), any()))
                .thenAnswer(invocation -> invocation.getArgument(0, String.class));
        when(notifyMessageService.createNotifyMessage(any(), any(), any(), any(), any()))
                .thenReturn(10001L);
    }

    @Test
    public void testSendMessageWhenProcessInstanceApprove_ignoreMissingMobile() {
        doThrow(new ServiceException(SMS_SEND_MOBILE_NOT_EXISTS))
                .when(smsSendApi).sendSingleSmsToAdmin(any());

        BpmMessageSendWhenProcessInstanceApproveReqDTO reqDTO = new BpmMessageSendWhenProcessInstanceApproveReqDTO();
        reqDTO.setStartUserId(227L);
        reqDTO.setProcessInstanceId("process-001");
        reqDTO.setProcessInstanceName("外出申请");

        assertDoesNotThrow(() -> bpmMessageService.sendMessageWhenProcessInstanceApprove(reqDTO));

        verify(smsSendApi).sendSingleSmsToAdmin(any());
        verify(notifyMessageService).createNotifyMessage(eq(227L), eq(2), any(), any(), any());
        verify(webSocketSenderApi).sendObject(eq(2), eq(227L), eq("notice-push"), any());
    }

    @Test
    public void testSendMessageWhenProcessInstanceReject_createNotifyAndPush() {
        BpmMessageSendWhenProcessInstanceRejectReqDTO reqDTO = new BpmMessageSendWhenProcessInstanceRejectReqDTO();
        reqDTO.setStartUserId(228L);
        reqDTO.setProcessInstanceId("process-002");
        reqDTO.setProcessInstanceName("请假申请");
        reqDTO.setReason("资料不完整");

        assertDoesNotThrow(() -> bpmMessageService.sendMessageWhenProcessInstanceReject(reqDTO));

        verify(smsSendApi).sendSingleSmsToAdmin(any());
        verify(notifyMessageService).createNotifyMessage(eq(228L), eq(2), any(), any(), any());
        verify(webSocketSenderApi).sendObject(eq(2), eq(228L), eq("notice-push"), any());
        verifyNoMoreInteractions(webSocketSenderApi);
    }
}
