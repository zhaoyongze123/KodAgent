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

/**
 * 通知公告站内信模板初始化。
 *
 * <p>公告推送需要同时写入 system_notify_message，这里启动时幂等补齐模板，
 * 避免环境缺少模板导致推送只走 websocket 而不落消息中心。</p>
 */
@Component
@Slf4j
public class SystemNoticeNotifyTemplateInitRunner implements ApplicationRunner {

    public static final String SYSTEM_NOTICE_NOTIFY_TEMPLATE_CODE = "system_notice_push";

    @Resource
    private NotifyTemplateService notifyTemplateService;

    @Override
    public void run(ApplicationArguments args) {
        if (notifyTemplateService.getNotifyTemplateByCodeFromCache(SYSTEM_NOTICE_NOTIFY_TEMPLATE_CODE) != null) {
            return;
        }
        NotifyTemplateSaveReqVO createReqVO = new NotifyTemplateSaveReqVO();
        createReqVO.setName("【系统】通知公告推送");
        createReqVO.setCode(SYSTEM_NOTICE_NOTIFY_TEMPLATE_CODE);
        createReqVO.setType(NotifyTemplateTypeEnum.NOTIFICATION_MESSAGE.getType());
        createReqVO.setNickname("公告中心");
        createReqVO.setContent("公告通知：{title}。{content}");
        createReqVO.setStatus(CommonStatusEnum.ENABLE.getStatus());
        createReqVO.setRemark("通知公告推送模板，供管理后台消息中心和实时通知共用");
        Long templateId = notifyTemplateService.createNotifyTemplate(createReqVO);
        log.info("[run][已自动初始化通知公告站内信模板，templateId={} code={}]", templateId, SYSTEM_NOTICE_NOTIFY_TEMPLATE_CODE);
    }
}
