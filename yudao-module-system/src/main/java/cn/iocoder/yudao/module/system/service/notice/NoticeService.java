package cn.iocoder.yudao.module.system.service.notice;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.system.controller.admin.notice.vo.NoticePageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.notice.vo.NoticeRespVO;
import cn.iocoder.yudao.module.system.controller.admin.notice.vo.NoticeSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.notice.NoticeDO;

import java.util.List;
import java.util.Set;

/**
 * 通知公告 Service 接口
 */
public interface NoticeService {

    /**
     * 创建通知公告
     *
     * @param createReqVO 通知公告
     * @return 编号
     */
    Long createNotice(NoticeSaveReqVO createReqVO);

    /**
     * 更新通知公告
     *
     * @param reqVO 通知公告
     */
    void updateNotice(NoticeSaveReqVO reqVO);

    /**
     * 删除通知公告
     *
     * @param id 编号
     */
    void deleteNotice(Long id);

    /**
     * 批量删除通知公告
     *
     * @param ids 编号列表
     */
    void deleteNoticeList(List<Long> ids);

    /**
     * 获得通知公告分页列表
     *
     * @param reqVO 分页条件
     * @return 部门分页列表
     */
    PageResult<NoticeDO> getNoticePage(NoticePageReqVO reqVO);

    /**
     * 获得通知公告
     *
     * @param id 编号
     * @return 通知公告
     */
    NoticeDO getNotice(Long id);

    /**
     * 获得通知公告详情
     *
     * @param id 编号
     * @return 通知公告详情
     */
    NoticeRespVO getNoticeDetail(Long id);

    /**
     * 申请通知公告附件的短时本地预览地址。
     *
     * @param id     公告编号
     * @param fileId 附件编号
     * @param userId 当前用户编号
     * @return 预览源地址
     */
    String getNoticeAttachmentPreviewUrl(Long id, Long fileId, Long userId);

    /**
     * 标记通知公告为已读
     *
     * @param id 编号
     * @param userId 用户编号
     * @param userNickname 用户昵称
     */
    void markNoticeRead(Long id, Long userId, String userNickname);

    /**
     * 解析通知公告分发到的用户编号列表
     *
     * @param id 公告编号
     * @return 用户编号集合
     */
    Set<Long> getNoticeTargetUserIds(Long id);

}
