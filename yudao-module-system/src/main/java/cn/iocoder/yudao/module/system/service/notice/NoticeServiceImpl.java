package cn.iocoder.yudao.module.system.service.notice;

import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.util.StrUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.collection.CollectionUtils;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.infra.dal.dataobject.file.FileDO;
import cn.iocoder.yudao.module.infra.service.file.FileService;
import cn.iocoder.yudao.module.system.controller.admin.notice.vo.NoticeAttachmentRespVO;
import cn.iocoder.yudao.module.system.controller.admin.notice.vo.NoticePageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.notice.vo.NoticeReadRespVO;
import cn.iocoder.yudao.module.system.controller.admin.notice.vo.NoticeRespVO;
import cn.iocoder.yudao.module.system.controller.admin.notice.vo.NoticeSaveReqVO;
import cn.iocoder.yudao.module.system.controller.admin.notice.vo.NoticeTargetReqVO;
import cn.iocoder.yudao.module.system.controller.admin.notice.vo.NoticeTargetRespVO;
import cn.iocoder.yudao.module.system.controller.admin.notice.vo.NoticeUnreadRespVO;
import cn.iocoder.yudao.module.system.dal.dataobject.dept.DeptDO;
import cn.iocoder.yudao.module.system.dal.dataobject.notice.NoticeDO;
import cn.iocoder.yudao.module.system.dal.dataobject.notice.NoticeReadDO;
import cn.iocoder.yudao.module.system.dal.dataobject.notice.NoticeTargetDO;
import cn.iocoder.yudao.module.system.dal.dataobject.permission.RoleDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.dal.mysql.notice.NoticeMapper;
import cn.iocoder.yudao.module.system.dal.mysql.notice.NoticeReadMapper;
import cn.iocoder.yudao.module.system.dal.mysql.notice.NoticeTargetMapper;
import cn.iocoder.yudao.module.system.enums.partyfile.PartyFileTargetTypeEnum;
import cn.iocoder.yudao.module.system.service.dept.DeptService;
import cn.iocoder.yudao.module.system.service.filepreview.AttachmentPreviewTokenService;
import cn.iocoder.yudao.module.system.service.permission.PermissionService;
import cn.iocoder.yudao.module.system.service.permission.RoleService;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import com.google.common.annotations.VisibleForTesting;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.NOTICE_TARGET_ALL_CONFLICT;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.NOTICE_TARGET_ID_REQUIRED;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.NOTICE_TARGET_TYPE_INVALID;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.NOTICE_ATTACHMENT_NOT_FOUND;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.NOTICE_NOT_FOUND;

/**
 * 通知公告 Service 实现类
 *
 * @author 芋道源码
 */
@Service
public class NoticeServiceImpl implements NoticeService {

    @Resource
    private NoticeMapper noticeMapper;

    @Resource
    private NoticeReadMapper noticeReadMapper;

    @Resource
    private NoticeTargetMapper noticeTargetMapper;

    @Resource
    private FileService fileService;

    @Resource
    private AttachmentPreviewTokenService attachmentPreviewTokenService;

    @Resource
    private AdminUserService adminUserService;

    @Resource
    private DeptService deptService;

    @Resource
    private RoleService roleService;

    @Resource
    private PermissionService permissionService;

    @Override
    public Long createNotice(NoticeSaveReqVO createReqVO) {
        List<NoticeTargetReqVO> targets = normalizeTargets(createReqVO.getTargets());
        validateTargets(targets);
        NoticeDO notice = BeanUtils.toBean(createReqVO, NoticeDO.class);
        notice.setPublishTarget(buildTargetSummary(targets));
        noticeMapper.insert(notice);
        saveTargets(notice.getId(), targets);
        return notice.getId();
    }

    @Override
    public void updateNotice(NoticeSaveReqVO updateReqVO) {
        // 校验是否存在
        validateNoticeExists(updateReqVO.getId());
        List<NoticeTargetReqVO> targets = normalizeTargets(updateReqVO.getTargets());
        validateTargets(targets);
        // 更新通知公告
        NoticeDO updateObj = BeanUtils.toBean(updateReqVO, NoticeDO.class);
        updateObj.setPublishTarget(buildTargetSummary(targets));
        noticeMapper.updateById(updateObj);
        noticeTargetMapper.deleteByNoticeId(updateReqVO.getId());
        saveTargets(updateReqVO.getId(), targets);
    }

    @Override
    public void deleteNotice(Long id) {
        // 校验是否存在
        validateNoticeExists(id);
        // 删除通知公告
        noticeMapper.deleteById(id);
        noticeTargetMapper.deleteByNoticeId(id);
        noticeReadMapper.delete(new cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX<NoticeReadDO>()
                .eq(NoticeReadDO::getNoticeId, id));
    }

    @Override
    public void deleteNoticeList(List<Long> ids) {
        noticeMapper.deleteByIds(ids);
        noticeTargetMapper.deleteByNoticeIds(ids);
        noticeReadMapper.delete(new cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX<NoticeReadDO>()
                .inIfPresent(NoticeReadDO::getNoticeId, ids));
    }

    @Override
    public PageResult<NoticeDO> getNoticePage(NoticePageReqVO reqVO) {
        return noticeMapper.selectPage(reqVO);
    }

    @Override
    public NoticeDO getNotice(Long id) {
        return noticeMapper.selectById(id);
    }

    @Override
    public NoticeRespVO getNoticeDetail(Long id) {
        NoticeDO notice = getNotice(id);
        if (notice == null) {
            return null;
        }
        NoticeRespVO detail = BeanUtils.toBean(notice, NoticeRespVO.class);
        List<NoticeReadDO> readList = noticeReadMapper.selectListByNoticeId(id);
        List<NoticeTargetDO> targetList = getNoticeTargetList(id);
        List<NoticeTargetRespVO> targets = buildTargetRespList(targetList);
        Set<Long> targetUserIds = resolveTargetUserIds(targetList);
        List<AdminUserDO> targetUsers = targetUserIds.isEmpty()
                ? Collections.emptyList()
                : adminUserService.getUserList(targetUserIds);
        Map<Long, DeptDO> deptMap = deptService.getDeptMap(CollectionUtils.convertSet(targetUsers, AdminUserDO::getDeptId));
        Map<Long, NoticeReadDO> readMap = CollectionUtils.convertMap(readList, NoticeReadDO::getUserId, Function.identity());
        detail.setTargets(targets);
        detail.setReadCount((long) readList.size());
        detail.setUnreadCount((long) Math.max(targetUsers.size() - readList.size(), 0));
        detail.setReadList(buildReadRespList(readList, targetUsers, deptMap));
        detail.setUnreadList(buildUnreadRespList(targetUsers, deptMap, readMap));
        detail.setAttachments(buildAttachments(notice.getAttachmentFileIds()));
        return detail;
    }

    @Override
    public String getNoticeAttachmentPreviewUrl(Long id, Long fileId, Long userId) {
        NoticeDO notice = noticeMapper.selectById(id);
        if (notice == null) {
            throw exception(NOTICE_NOT_FOUND);
        }
        if (!parseFileIds(notice.getAttachmentFileIds()).contains(fileId)) {
            throw exception(NOTICE_ATTACHMENT_NOT_FOUND);
        }
        FileDO file = fileService.getFile(fileId);
        return attachmentPreviewTokenService.createPreviewUrl(
                AttachmentPreviewTokenService.PreviewSource.NOTICE,
                id, fileId, userId, file.getName());
    }

    @Override
    public void markNoticeRead(Long id, Long userId, String userNickname) {
        validateNoticeExists(id);
        if (userId == null) {
            return;
        }
        NoticeReadDO existed = noticeReadMapper.selectByNoticeIdAndUserId(id, userId);
        if (existed != null) {
            existed.setReadTime(LocalDateTime.now());
            existed.setUserNickname(StrUtil.blankToDefault(userNickname, existed.getUserNickname()));
            noticeReadMapper.updateById(existed);
            return;
        }
        NoticeReadDO readDO = new NoticeReadDO();
        readDO.setNoticeId(id);
        readDO.setUserId(userId);
        readDO.setUserNickname(StrUtil.blankToDefault(userNickname, "未命名用户"));
        readDO.setReadTime(LocalDateTime.now());
        noticeReadMapper.insert(readDO);
    }

    @Override
    public Set<Long> getNoticeTargetUserIds(Long id) {
        validateNoticeExists(id);
        return resolveTargetUserIds(getNoticeTargetList(id));
    }

    private void saveTargets(Long noticeId, List<NoticeTargetReqVO> targets) {
        List<NoticeTargetDO> targetDOs = targets.stream().map(item -> {
            NoticeTargetDO targetDO = new NoticeTargetDO();
            targetDO.setNoticeId(noticeId);
            targetDO.setTargetType(item.getTargetType());
            targetDO.setTargetId(item.getTargetId());
            return targetDO;
        }).collect(Collectors.toList());
        noticeTargetMapper.insertBatch(targetDOs);
    }

    private List<NoticeTargetReqVO> normalizeTargets(List<NoticeTargetReqVO> targets) {
        if (CollUtil.isNotEmpty(targets)) {
            return targets;
        }
        NoticeTargetReqVO allTarget = new NoticeTargetReqVO();
        allTarget.setTargetType(PartyFileTargetTypeEnum.ALL.getType());
        return Collections.singletonList(allTarget);
    }

    private List<NoticeTargetDO> getNoticeTargetList(Long noticeId) {
        List<NoticeTargetDO> targets = noticeTargetMapper.selectListByNoticeId(noticeId);
        if (CollUtil.isNotEmpty(targets)) {
            return targets;
        }
        NoticeTargetDO allTarget = new NoticeTargetDO();
        allTarget.setNoticeId(noticeId);
        allTarget.setTargetType(PartyFileTargetTypeEnum.ALL.getType());
        return Collections.singletonList(allTarget);
    }

    private void validateTargets(List<NoticeTargetReqVO> targets) {
        boolean hasAll = false;
        Set<Long> userIds = new LinkedHashSet<>();
        Set<Long> deptIds = new LinkedHashSet<>();
        Set<Long> roleIds = new LinkedHashSet<>();
        for (NoticeTargetReqVO target : targets) {
            if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.ALL.getType())) {
                hasAll = true;
                continue;
            }
            if (target.getTargetId() == null) {
                throw exception(NOTICE_TARGET_ID_REQUIRED);
            }
            if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.USER.getType())) {
                userIds.add(target.getTargetId());
            } else if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.DEPT.getType())) {
                deptIds.add(target.getTargetId());
            } else if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.ROLE.getType())) {
                roleIds.add(target.getTargetId());
            } else {
                throw exception(NOTICE_TARGET_TYPE_INVALID);
            }
        }
        if (hasAll && targets.size() > 1) {
            throw exception(NOTICE_TARGET_ALL_CONFLICT);
        }
        if (CollUtil.isNotEmpty(userIds)) {
            adminUserService.validateUserList(userIds);
        }
        if (CollUtil.isNotEmpty(deptIds)) {
            deptService.validateDeptList(deptIds);
        }
        if (CollUtil.isNotEmpty(roleIds)) {
            roleService.validateRoleList(roleIds);
        }
    }

    private String buildTargetSummary(List<NoticeTargetReqVO> targets) {
        List<NoticeTargetDO> targetDOs = targets.stream().map(item -> {
            NoticeTargetDO targetDO = new NoticeTargetDO();
            targetDO.setTargetType(item.getTargetType());
            targetDO.setTargetId(item.getTargetId());
            return targetDO;
        }).collect(Collectors.toList());
        List<NoticeTargetRespVO> targetRespList = buildTargetRespList(targetDOs);
        return targetRespList.stream()
                .map(NoticeTargetRespVO::getTargetName)
                .filter(StrUtil::isNotBlank)
                .collect(Collectors.joining("、"));
    }

    private Set<Long> resolveTargetUserIds(List<NoticeTargetDO> targetList) {
        if (targetList.isEmpty()
                || targetList.stream().anyMatch(item -> Objects.equals(item.getTargetType(), PartyFileTargetTypeEnum.ALL.getType()))) {
            return CollectionUtils.convertSet(adminUserService.getUserListByStatus(0), AdminUserDO::getId);
        }
        Set<Long> userIds = new LinkedHashSet<>();
        Set<Long> directUserIds = targetList.stream()
                .filter(item -> Objects.equals(item.getTargetType(), PartyFileTargetTypeEnum.USER.getType()))
                .map(NoticeTargetDO::getTargetId)
                .collect(Collectors.toSet());
        if (CollUtil.isNotEmpty(directUserIds)) {
            userIds.addAll(directUserIds);
        }
        Set<Long> deptIds = targetList.stream()
                .filter(item -> Objects.equals(item.getTargetType(), PartyFileTargetTypeEnum.DEPT.getType()))
                .map(NoticeTargetDO::getTargetId)
                .collect(Collectors.toSet());
        if (CollUtil.isNotEmpty(deptIds)) {
            Set<Long> allDeptIds = new LinkedHashSet<>(deptIds);
            deptIds.forEach(deptId -> allDeptIds.addAll(deptService.getChildDeptIdListFromCache(deptId)));
            userIds.addAll(CollectionUtils.convertSet(adminUserService.getUserListByDeptIds(allDeptIds), AdminUserDO::getId));
        }
        Set<Long> roleIds = targetList.stream()
                .filter(item -> Objects.equals(item.getTargetType(), PartyFileTargetTypeEnum.ROLE.getType()))
                .map(NoticeTargetDO::getTargetId)
                .collect(Collectors.toSet());
        if (CollUtil.isNotEmpty(roleIds)) {
            userIds.addAll(permissionService.getUserRoleIdListByRoleId(roleIds));
        }
        return userIds;
    }

    private List<NoticeAttachmentRespVO> buildAttachments(String attachmentFileIds) {
        List<Long> fileIds = parseFileIds(attachmentFileIds);
        if (CollUtil.isEmpty(fileIds)) {
            return Collections.emptyList();
        }
        List<NoticeAttachmentRespVO> attachments = new ArrayList<>();
        for (Long fileId : fileIds) {
            FileDO file = fileService.getFile(fileId);
            if (file == null) {
                continue;
            }
            NoticeAttachmentRespVO attachment = new NoticeAttachmentRespVO();
            attachment.setId(file.getId());
            attachment.setName(file.getName());
            attachment.setUrl(file.getUrl());
            attachment.setType(file.getType());
            attachment.setSize(file.getSize());
            attachments.add(attachment);
        }
        return attachments;
    }

    private List<Long> parseFileIds(String attachmentFileIds) {
        if (StrUtil.isBlank(attachmentFileIds)) {
            return Collections.emptyList();
        }
        return StrUtil.splitTrim(attachmentFileIds, ',').stream()
                .map(item -> StrUtil.isBlank(item) ? null : Long.valueOf(item))
                .filter(Objects::nonNull)
                .collect(Collectors.toList());
    }

    private List<NoticeTargetRespVO> buildTargetRespList(List<NoticeTargetDO> targetList) {
        Set<Long> userIds = new LinkedHashSet<>();
        Set<Long> deptIds = new LinkedHashSet<>();
        Set<Long> roleIds = new LinkedHashSet<>();
        for (NoticeTargetDO target : targetList) {
            if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.USER.getType())) {
                userIds.add(target.getTargetId());
            } else if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.DEPT.getType())) {
                deptIds.add(target.getTargetId());
            } else if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.ROLE.getType())) {
                roleIds.add(target.getTargetId());
            }
        }
        Map<Long, String> userNameMap = CollectionUtils.convertMap(adminUserService.getUserList(userIds),
                AdminUserDO::getId, AdminUserDO::getNickname);
        Map<Long, String> deptNameMap = CollectionUtils.convertMap(deptService.getDeptList(deptIds),
                DeptDO::getId, DeptDO::getName);
        Map<Long, String> roleNameMap = CollectionUtils.convertMap(roleService.getRoleList(roleIds),
                RoleDO::getId, RoleDO::getName);
        return targetList.stream().map(target -> {
            NoticeTargetRespVO respVO = new NoticeTargetRespVO();
            respVO.setTargetType(target.getTargetType());
            respVO.setTargetId(target.getTargetId());
            if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.ALL.getType())) {
                respVO.setTargetName("全体后台用户");
            } else if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.USER.getType())) {
                respVO.setTargetName(userNameMap.get(target.getTargetId()));
            } else if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.DEPT.getType())) {
                respVO.setTargetName(deptNameMap.get(target.getTargetId()));
            } else if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.ROLE.getType())) {
                respVO.setTargetName(roleNameMap.get(target.getTargetId()));
            }
            return respVO;
        }).collect(Collectors.toList());
    }

    private List<NoticeReadRespVO> buildReadRespList(List<NoticeReadDO> readList, List<AdminUserDO> users, Map<Long, DeptDO> deptMap) {
        Map<Long, AdminUserDO> userMap = CollectionUtils.convertMap(users, AdminUserDO::getId, Function.identity());
        return readList.stream().map(item -> {
            NoticeReadRespVO respVO = new NoticeReadRespVO();
            respVO.setUserId(item.getUserId());
            respVO.setUserNickname(item.getUserNickname());
            respVO.setReadTime(item.getReadTime());
            AdminUserDO user = userMap.get(item.getUserId());
            if (user != null) {
                respVO.setDeptId(user.getDeptId());
                DeptDO dept = deptMap.get(user.getDeptId());
                respVO.setDeptName(dept == null ? null : dept.getName());
            }
            return respVO;
        }).collect(Collectors.toList());
    }

    private List<NoticeUnreadRespVO> buildUnreadRespList(List<AdminUserDO> users, Map<Long, DeptDO> deptMap,
                                                         Map<Long, NoticeReadDO> readMap) {
        return users.stream()
                .filter(user -> !readMap.containsKey(user.getId()))
                .map(user -> {
                    NoticeUnreadRespVO respVO = new NoticeUnreadRespVO();
                    respVO.setUserId(user.getId());
                    respVO.setUserNickname(user.getNickname());
                    respVO.setDeptId(user.getDeptId());
                    DeptDO dept = deptMap.get(user.getDeptId());
                    respVO.setDeptName(dept == null ? null : dept.getName());
                    return respVO;
                })
                .collect(Collectors.toList());
    }

    @VisibleForTesting
    public void validateNoticeExists(Long id) {
        if (id == null) {
            return;
        }
        NoticeDO notice = noticeMapper.selectById(id);
        if (notice == null) {
            throw exception(NOTICE_NOT_FOUND);
        }
    }

}
