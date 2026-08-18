package cn.iocoder.yudao.module.system.framework.notify;

import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.module.system.controller.admin.notify.vo.template.NotifyTemplateSaveReqVO;
import cn.iocoder.yudao.module.system.enums.notify.NotifyTemplateTypeEnum;
import cn.iocoder.yudao.module.system.service.notify.NotifyTemplateService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

@Component
@Slf4j
public class SystemMeetingBookingNotifyTemplateInitRunner implements ApplicationRunner {

    public static final String MEETING_BOOKING_CANCEL_NOTICE_TEMPLATE_CODE = "system_meeting_booking_cancel_notice";
    public static final String MEETING_BOOKING_CONFLICT_NOTICE_TEMPLATE_CODE = "system_meeting_booking_conflict_notice";
    public static final String MEETING_BOOKING_UPDATE_NOTICE_TEMPLATE_CODE = "system_meeting_booking_update_notice";

    @Resource
    private NotifyTemplateService notifyTemplateService;

    @Override
    public void run(ApplicationArguments args) {
        initTemplate(MEETING_BOOKING_CANCEL_NOTICE_TEMPLATE_CODE, "【会议室】预定已取消",
                "你的会议室预定【{subject}】已被取消，会议室：{roomName}，时间：{startTime} - {endTime}，原因：{cancelReason}");
        initTemplate(MEETING_BOOKING_CONFLICT_NOTICE_TEMPLATE_CODE, "【会议室】预定冲突提醒",
                "你的会议室预定与其他记录发生冲突。会议主题：{subject}，会议室：{roomName}，时间：{startTime} - {endTime}，记录编号：{bookingId}");
        initTemplate(MEETING_BOOKING_UPDATE_NOTICE_TEMPLATE_CODE, "【会议室】预定已变更",
                "你的会议室预定已被管理员修改。会议主题：{subject}，会议室：{roomName}，时间：{startTime} - {endTime}");
    }

    private void initTemplate(String code, String name, String content) {
        if (notifyTemplateService.getNotifyTemplateByCodeFromCache(code) != null) {
            return;
        }
        NotifyTemplateSaveReqVO createReqVO = new NotifyTemplateSaveReqVO();
        createReqVO.setName(name);
        createReqVO.setCode(code);
        createReqVO.setType(NotifyTemplateTypeEnum.NOTIFICATION_MESSAGE.getType());
        createReqVO.setNickname("会议室预定");
        createReqVO.setContent(content);
        createReqVO.setStatus(CommonStatusEnum.ENABLE.getStatus());
        createReqVO.setRemark("会议室预定模块自动初始化模板");
        Long templateId = notifyTemplateService.createNotifyTemplate(createReqVO);
        log.info("[initTemplate][已自动初始化会议室站内信模板，templateId={} code={}]", templateId, code);
    }

}
