package cn.iocoder.yudao.module.system.service.notify;

import cn.hutool.core.convert.Convert;
import cn.iocoder.yudao.module.system.dal.dataobject.notice.NoticeDO;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.system.controller.admin.notify.vo.message.NotifyMessageMyPageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.notify.vo.message.NotifyMessagePageReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.notify.NotifyMessageDO;
import cn.iocoder.yudao.module.system.dal.dataobject.notify.NotifyTemplateDO;
import cn.iocoder.yudao.module.system.dal.mysql.notify.NotifyMessageMapper;
import cn.iocoder.yudao.module.system.framework.notify.SystemNoticeNotifyTemplateInitRunner;
import cn.iocoder.yudao.module.system.service.notice.NoticeService;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * 站内信 Service 实现类
 *
 * @author xrcoder
 */
@Service
@Validated
public class NotifyMessageServiceImpl implements NotifyMessageService {

    @Resource
    private NotifyMessageMapper notifyMessageMapper;

    @Resource
    private NoticeService noticeService;

    @Override
    public Long createNotifyMessage(Long userId, Integer userType,
                                    NotifyTemplateDO template, String templateContent, Map<String, Object> templateParams) {
        NotifyMessageDO message = new NotifyMessageDO().setUserId(userId).setUserType(userType)
                .setTemplateId(template.getId()).setTemplateCode(template.getCode())
                .setTemplateType(template.getType()).setTemplateNickname(template.getNickname())
                .setTemplateContent(templateContent).setTemplateParams(templateParams).setReadStatus(false);
        notifyMessageMapper.insert(message);
        return message.getId();
    }

    @Override
    public PageResult<NotifyMessageDO> getNotifyMessagePage(NotifyMessagePageReqVO pageReqVO) {
        return notifyMessageMapper.selectPage(pageReqVO);
    }

    @Override
    public PageResult<NotifyMessageDO> getMyMyNotifyMessagePage(NotifyMessageMyPageReqVO pageReqVO, Long userId, Integer userType) {
        return notifyMessageMapper.selectPage(pageReqVO, userId, userType);
    }

    @Override
    public NotifyMessageDO getNotifyMessage(Long id) {
        return notifyMessageMapper.selectById(id);
    }

    @Override
    public List<NotifyMessageDO> getUnreadNotifyMessageList(Long userId, Integer userType, Integer size) {
        return notifyMessageMapper.selectUnreadListByUserIdAndUserType(userId, userType, size);
    }

    @Override
    public Long getUnreadNotifyMessageCount(Long userId, Integer userType) {
        return notifyMessageMapper.selectUnreadCountByUserIdAndUserType(userId, userType);
    }

    @Override
    public int updateNotifyMessageRead(Collection<Long> ids, Long userId, Integer userType) {
        return notifyMessageMapper.updateListRead(ids, userId, userType);
    }

    @Override
    public int updateNotifyMessageRead(Collection<Long> ids, Long userId, Integer userType, String userNickname) {
        List<NotifyMessageDO> messages = notifyMessageMapper.selectListByIdsAndUser(ids, userId, userType);
        int updated = notifyMessageMapper.updateListRead(ids, userId, userType);
        syncNoticeRead(messages, userId, userNickname);
        return updated;
    }

    @Override
    public int updateAllNotifyMessageRead(Long userId, Integer userType) {
        return notifyMessageMapper.updateListRead(userId, userType);
    }

    @Override
    public int updateAllNotifyMessageRead(Long userId, Integer userType, String userNickname) {
        List<NotifyMessageDO> messages = notifyMessageMapper.selectUnreadListByUser(userId, userType);
        int updated = notifyMessageMapper.updateListRead(userId, userType);
        syncNoticeRead(messages, userId, userNickname);
        return updated;
    }

    private void syncNoticeRead(List<NotifyMessageDO> messages, Long userId, String userNickname) {
        if (messages == null || messages.isEmpty()) {
            return;
        }
        List<Long> noticeIds = messages.stream()
                .filter(message -> SystemNoticeNotifyTemplateInitRunner.SYSTEM_NOTICE_NOTIFY_TEMPLATE_CODE
                        .equals(message.getTemplateCode()))
                .map(this::extractNoticeId)
                .filter(Objects::nonNull)
                .distinct()
                .collect(Collectors.toList());
        if (noticeIds.isEmpty()) {
            return;
        }
        noticeIds.forEach(noticeId -> noticeService.markNoticeRead(noticeId, userId, userNickname));
    }

    private Long extractNoticeId(NotifyMessageDO message) {
        Map<String, Object> params = message.getTemplateParams();
        if (params == null || params.isEmpty()) {
            return null;
        }
        return Convert.toLong(params.get("noticeId"));
    }

}
