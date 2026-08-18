package cn.iocoder.yudao.module.system.service.partyfile;

import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.util.StrUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.collection.CollectionUtils;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.infra.dal.dataobject.file.FileDO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.*;
import cn.iocoder.yudao.module.system.dal.dataobject.dept.DeptDO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.*;
import cn.iocoder.yudao.module.system.dal.dataobject.permission.RoleDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.dal.mysql.partyfile.PartyFileMapper;
import cn.iocoder.yudao.module.system.dal.mysql.partyfile.PartyFileReadMapper;
import cn.iocoder.yudao.module.system.dal.mysql.partyfile.PartyFileTargetMapper;
import cn.iocoder.yudao.module.system.enums.partyfile.PartyFileReadSourceEnum;
import cn.iocoder.yudao.module.system.enums.partyfile.PartyFileStorageTypeEnum;
import cn.iocoder.yudao.module.system.enums.partyfile.PartyFileTargetTypeEnum;
import cn.iocoder.yudao.module.system.service.dept.DeptService;
import cn.iocoder.yudao.module.system.service.permission.PermissionService;
import cn.iocoder.yudao.module.system.service.permission.RoleService;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.time.LocalDateTime;
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.*;

@Service
@Validated
public class PartyFileServiceImpl implements PartyFileService {

    @Resource
    private PartyFileMapper partyFileMapper;
    @Resource
    private PartyFileTargetMapper partyFileTargetMapper;
    @Resource
    private PartyFileReadMapper partyFileReadMapper;
    @Resource
    private PartyFileCategoryService partyFileCategoryService;
    @Resource
    private PartyFileAttachmentService partyFileAttachmentService;
    @Resource
    private PartyFileKodSourceServiceImpl partyFileKodSourceService;
    @Resource
    private AdminUserService adminUserService;
    @Resource
    private DeptService deptService;
    @Resource
    private RoleService roleService;
    @Resource
    private PermissionService permissionService;

    @Override
    public Long createPartyFile(PartyFileSaveReqVO reqVO) {
        validateCategoryExists(reqVO.getCategoryId());
        validateTargets(reqVO.getTargets());
        validateStorageConfig(reqVO);
        PartyFileDO partyFile = BeanUtils.toBean(reqVO, PartyFileDO.class);
        partyFileMapper.insert(partyFile);
        saveTargets(partyFile.getId(), reqVO.getTargets());
        return partyFile.getId();
    }

    @Override
    public void updatePartyFile(PartyFileSaveReqVO reqVO) {
        validatePartyFileExists(reqVO.getId());
        validateCategoryExists(reqVO.getCategoryId());
        validateTargets(reqVO.getTargets());
        validateStorageConfig(reqVO);
        PartyFileDO updateObj = BeanUtils.toBean(reqVO, PartyFileDO.class);
        partyFileMapper.updateById(updateObj);
        partyFileTargetMapper.deleteByPartyFileId(reqVO.getId());
        saveTargets(reqVO.getId(), reqVO.getTargets());
    }

    @Override
    public void deletePartyFile(Long id) {
        validatePartyFileExists(id);
        partyFileMapper.deleteById(id);
        partyFileTargetMapper.deleteByPartyFileId(id);
        partyFileReadMapper.deleteByPartyFileId(id);
    }

    @Override
    public PageResult<PartyFileRespVO> getPartyFilePage(PartyFilePageReqVO reqVO) {
        PageResult<PartyFileDO> pageResult = partyFileMapper.selectPage(reqVO);
        return buildPageResult(pageResult, null);
    }

    @Override
    public PartyFileRespVO getPartyFileDetail(Long id) {
        PartyFileDO partyFile = validatePartyFileExists(id);
        return buildDetailResp(partyFile, null, false, null, null);
    }

    @Override
    public PageResult<PartyFileRespVO> getMyPartyFilePage(Long userId, PartyFileMyPageReqVO reqVO) {
        Set<Long> visibleFileIds = getVisibleFileIds(userId);
        if (visibleFileIds.isEmpty()) {
            return new PageResult<>(Collections.emptyList(), 0L);
        }
        PageResult<PartyFileDO> pageResult = partyFileMapper.selectMyPage(reqVO, visibleFileIds);
        PageResult<PartyFileRespVO> respPage = buildPageResult(pageResult, userId);
        if (reqVO.getReadStatus() == null) {
            return respPage;
        }
        List<PartyFileRespVO> filtered = respPage.getList().stream()
                .filter(item -> Objects.equals(item.getReadStatus(), reqVO.getReadStatus()))
                .collect(Collectors.toList());
        return new PageResult<PartyFileRespVO>(filtered, (long) filtered.size());
    }

    @Override
    public PartyFileRespVO getMyPartyFileDetail(Long id, Long userId, String userNickname) {
        PartyFileDO partyFile = validateReadable(id, userId);
        markRead(id, userId, userNickname, PartyFileReadSourceEnum.DETAIL.getSource());
        return buildDetailResp(partyFile, userId, true, userNickname, PartyFileReadSourceEnum.DETAIL.getSource());
    }

    @Override
    public PartyFileRespVO getMyPartyFileAttachment(Long id, Long fileId, Long userId, String userNickname, Integer readSource) {
        PartyFileDO partyFile = validateReadable(id, userId);
        validateAttachmentAccessible(partyFile, fileId);
        markRead(id, userId, userNickname, readSource);
        return buildDetailResp(partyFile, userId, true, userNickname, readSource);
    }

    @Override
    public void validateAttachmentAccessible(Long id, Long fileId) {
        validateAttachmentAccessible(validatePartyFileExists(id), fileId);
    }

    private PageResult<PartyFileRespVO> buildPageResult(PageResult<PartyFileDO> pageResult, Long userId) {
        if (CollUtil.isEmpty(pageResult.getList())) {
            return new PageResult<>(Collections.emptyList(), pageResult.getTotal());
        }
        Map<Long, String> categoryNameMap = buildCategoryNameMap(pageResult.getList());
        Map<String, String> creatorNameMap = buildCreatorNameMap(pageResult.getList());
        Map<Long, Boolean> readStatusMap = buildReadStatusMap(pageResult.getList(), userId);
        Map<Long, Long> readCountMap = buildReadCountMap(pageResult.getList());
        Map<Long, Integer> targetCountMap = buildTargetUserCountMap(pageResult.getList());
        List<PartyFileRespVO> list = pageResult.getList().stream().map(item -> {
            PartyFileRespVO respVO = BeanUtils.toBean(item, PartyFileRespVO.class);
            respVO.setCategoryName(categoryNameMap.get(item.getCategoryId()));
            respVO.setCreator(resolveCreatorName(item.getCreator(), creatorNameMap));
            respVO.setReadStatus(readStatusMap.getOrDefault(item.getId(), false));
            long readCount = readCountMap.getOrDefault(item.getId(), 0L);
            long unreadCount = Math.max(targetCountMap.getOrDefault(item.getId(), 0) - readCount, 0);
            respVO.setReadCount(readCount);
            respVO.setUnreadCount(unreadCount);
            return respVO;
        }).collect(Collectors.toList());
        return new PageResult<>(list, pageResult.getTotal());
    }

    private PartyFileRespVO buildDetailResp(PartyFileDO partyFile, Long userId, boolean includeReadStatus,
                                            String userNickname, Integer readSource) {
        PartyFileRespVO detail = BeanUtils.toBean(partyFile, PartyFileRespVO.class);
        detail.setCreator(resolveCreatorName(partyFile.getCreator(), buildCreatorNameMap(Collections.singletonList(partyFile))));
        PartyFileCategoryDO category = partyFileCategoryService.getCategory(partyFile.getCategoryId());
        detail.setCategoryName(category == null ? null : category.getName());
        detail.setAttachments(buildAttachments(partyFile.getAttachmentFileIds()));
        List<PartyFileTargetDO> targetList = partyFileTargetMapper.selectListByPartyFileId(partyFile.getId());
        detail.setTargets(buildTargetRespList(targetList));
        Set<Long> targetUserIds = resolveTargetUserIds(targetList);
        List<AdminUserDO> targetUsers = targetUserIds.isEmpty() ? Collections.emptyList() : adminUserService.getUserList(targetUserIds);
        Map<Long, DeptDO> deptMap = deptService.getDeptMap(CollectionUtils.convertSet(targetUsers, AdminUserDO::getDeptId));
        List<PartyFileReadDO> readList = partyFileReadMapper.selectListByPartyFileId(partyFile.getId());
        Map<Long, PartyFileReadDO> readMap = CollectionUtils.convertMap(readList, PartyFileReadDO::getUserId, Function.identity());
        detail.setReadCount((long) readList.size());
        detail.setUnreadCount((long) Math.max(targetUsers.size() - readList.size(), 0));
        detail.setReadList(buildReadRespList(readList, targetUsers, deptMap));
        detail.setUnreadList(buildUnreadRespList(targetUsers, deptMap, readMap));
        if (includeReadStatus && userId != null) {
            detail.setReadStatus(readMap.containsKey(userId));
        }
        return detail;
    }

    private Map<String, String> buildCreatorNameMap(Collection<PartyFileDO> partyFiles) {
        Set<Long> creatorIds = partyFiles.stream()
                .map(PartyFileDO::getCreator)
                .filter(StrUtil::isNotBlank)
                .filter(StrUtil::isNumeric)
                .map(Long::valueOf)
                .collect(Collectors.toSet());
        if (CollUtil.isEmpty(creatorIds)) {
            return Collections.emptyMap();
        }
        return adminUserService.getUserList(creatorIds).stream()
                .collect(Collectors.toMap(user -> String.valueOf(user.getId()),
                        user -> StrUtil.blankToDefault(user.getNickname(), user.getUsername()),
                        (left, right) -> left));
    }

    private String resolveCreatorName(String creator, Map<String, String> creatorNameMap) {
        if (StrUtil.isBlank(creator)) {
            return creator;
        }
        return creatorNameMap.getOrDefault(creator, creator);
    }

    private void saveTargets(Long partyFileId, List<PartyFileTargetReqVO> targets) {
        List<PartyFileTargetDO> targetDOs = targets.stream().map(item -> {
            PartyFileTargetDO targetDO = new PartyFileTargetDO();
            targetDO.setPartyFileId(partyFileId);
            targetDO.setTargetType(item.getTargetType());
            targetDO.setTargetId(item.getTargetId());
            return targetDO;
        }).collect(Collectors.toList());
        partyFileTargetMapper.insertBatch(targetDOs);
    }

    private void validateTargets(List<PartyFileTargetReqVO> targets) {
        boolean hasAll = false;
        Set<Long> userIds = new LinkedHashSet<>();
        Set<Long> deptIds = new LinkedHashSet<>();
        Set<Long> roleIds = new LinkedHashSet<>();
        for (PartyFileTargetReqVO target : targets) {
            if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.ALL.getType())) {
                hasAll = true;
                continue;
            }
            if (target.getTargetId() == null) {
                throw exception(PARTY_FILE_TARGET_ID_REQUIRED);
            }
            if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.USER.getType())) {
                userIds.add(target.getTargetId());
            } else if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.DEPT.getType())) {
                deptIds.add(target.getTargetId());
            } else if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.ROLE.getType())) {
                roleIds.add(target.getTargetId());
            } else {
                throw exception(PARTY_FILE_TARGET_TYPE_INVALID);
            }
        }
        if (hasAll && targets.size() > 1) {
            throw exception(PARTY_FILE_TARGET_ALL_CONFLICT);
        }
        if (!userIds.isEmpty()) {
            adminUserService.validateUserList(userIds);
        }
        if (!deptIds.isEmpty()) {
            deptService.validateDeptList(deptIds);
        }
        if (!roleIds.isEmpty()) {
            roleService.validateRoleList(roleIds);
        }
    }

    private void validateCategoryExists(Long categoryId) {
        if (partyFileCategoryService.getCategory(categoryId) == null) {
            throw exception(PARTY_FILE_CATEGORY_NOT_FOUND);
        }
    }

    private void validateStorageConfig(PartyFileSaveReqVO reqVO) {
        if (PartyFileStorageTypeEnum.isKod(reqVO.getStorageType())) {
            if (reqVO.getKodSourceId() == null || StrUtil.isBlank(reqVO.getKodFolderPath())) {
                throw exception(PARTY_FILE_STORAGE_CONFIG_INVALID);
            }
            PartyFileKodSourceDO source = partyFileKodSourceService.getEnabledSource(reqVO.getKodSourceId());
            reqVO.setKodFolderName(StrUtil.blankToDefault(reqVO.getKodFolderName(), source.getRootFolderName()));
            return;
        }
        reqVO.setKodSourceId(null);
        reqVO.setKodFolderPath(null);
        reqVO.setKodFolderName(null);
    }

    private PartyFileDO validatePartyFileExists(Long id) {
        PartyFileDO partyFile = partyFileMapper.selectById(id);
        if (partyFile == null) {
            throw exception(PARTY_FILE_NOT_FOUND);
        }
        return partyFile;
    }

    private PartyFileDO validateReadable(Long id, Long userId) {
        PartyFileDO partyFile = validatePartyFileExists(id);
        if (!Boolean.TRUE.equals(getVisibleFileIds(userId).contains(id))) {
            throw exception(PARTY_FILE_NOT_AUTHORIZED);
        }
        return partyFile;
    }

    private void markRead(Long id, Long userId, String userNickname, Integer readSource) {
        if (userId == null) {
            return;
        }
        PartyFileReadDO exists = partyFileReadMapper.selectByPartyFileIdAndUserId(id, userId);
        if (exists != null) {
            exists.setReadTime(LocalDateTime.now());
            exists.setReadSource(readSource);
            exists.setUserNickname(StrUtil.blankToDefault(userNickname, exists.getUserNickname()));
            partyFileReadMapper.updateById(exists);
            return;
        }
        PartyFileReadDO readDO = new PartyFileReadDO();
        readDO.setPartyFileId(id);
        readDO.setUserId(userId);
        readDO.setUserNickname(StrUtil.blankToDefault(userNickname, "未命名用户"));
        readDO.setReadTime(LocalDateTime.now());
        readDO.setReadSource(readSource);
        partyFileReadMapper.insert(readDO);
    }

    private Set<Long> getVisibleFileIds(Long userId) {
        if (userId == null) {
            return Collections.emptySet();
        }
        Set<Long> result = new LinkedHashSet<>();
        List<PartyFileTargetDO> allTargets = partyFileTargetMapper.selectListByTargetType(PartyFileTargetTypeEnum.ALL.getType());
        result.addAll(CollectionUtils.convertSet(allTargets, PartyFileTargetDO::getPartyFileId));
        AdminUserDO user = adminUserService.getUser(userId);
        if (user == null) {
            return result;
        }
        result.addAll(CollectionUtils.convertSet(
                partyFileTargetMapper.selectListByTarget(PartyFileTargetTypeEnum.USER.getType(), Collections.singleton(userId)),
                PartyFileTargetDO::getPartyFileId));
        if (user.getDeptId() != null) {
            Set<Long> deptIds = deptService.getChildDeptIdListFromCache(user.getDeptId());
            deptIds.add(user.getDeptId());
            result.addAll(CollectionUtils.convertSet(
                    partyFileTargetMapper.selectListByTarget(PartyFileTargetTypeEnum.DEPT.getType(), deptIds),
                    PartyFileTargetDO::getPartyFileId));
        }
        Set<Long> roleIds = permissionService.getUserRoleIdListByUserId(userId);
        if (CollUtil.isNotEmpty(roleIds)) {
            result.addAll(CollectionUtils.convertSet(
                    partyFileTargetMapper.selectListByTarget(PartyFileTargetTypeEnum.ROLE.getType(), roleIds),
                    PartyFileTargetDO::getPartyFileId));
        }
        return result;
    }

    private Map<Long, String> buildCategoryNameMap(List<PartyFileDO> partyFiles) {
        Set<Long> categoryIds = CollectionUtils.convertSet(partyFiles, PartyFileDO::getCategoryId);
        List<PartyFileCategoryDO> categories = partyFileCategoryService.getCategoryList(null).stream()
                .filter(item -> categoryIds.contains(item.getId()))
                .collect(Collectors.toList());
        return CollectionUtils.convertMap(categories, PartyFileCategoryDO::getId, PartyFileCategoryDO::getName);
    }

    private Map<Long, Boolean> buildReadStatusMap(List<PartyFileDO> partyFiles, Long userId) {
        if (userId == null || partyFiles.isEmpty()) {
            return Collections.emptyMap();
        }
        List<PartyFileReadDO> readList = partyFileReadMapper.selectListByPartyFileIdsAndUserId(
                CollectionUtils.convertSet(partyFiles, PartyFileDO::getId), userId);
        return readList.stream().collect(Collectors.toMap(PartyFileReadDO::getPartyFileId, item -> true));
    }

    private Map<Long, Long> buildReadCountMap(List<PartyFileDO> partyFiles) {
        Map<Long, Long> result = new HashMap<>();
        for (PartyFileDO partyFile : partyFiles) {
            result.put(partyFile.getId(), (long) partyFileReadMapper.selectListByPartyFileId(partyFile.getId()).size());
        }
        return result;
    }

    private Map<Long, Integer> buildTargetUserCountMap(List<PartyFileDO> partyFiles) {
        Map<Long, Integer> result = new HashMap<>();
        for (PartyFileDO partyFile : partyFiles) {
            List<PartyFileTargetDO> targets = partyFileTargetMapper.selectListByPartyFileId(partyFile.getId());
            result.put(partyFile.getId(), resolveTargetUserIds(targets).size());
        }
        return result;
    }

    private Set<Long> resolveTargetUserIds(List<PartyFileTargetDO> targetList) {
        if (targetList.isEmpty()) {
            return Collections.emptySet();
        }
        if (targetList.stream().anyMatch(item -> Objects.equals(item.getTargetType(), PartyFileTargetTypeEnum.ALL.getType()))) {
            return CollectionUtils.convertSet(adminUserService.getUserListByStatus(0), AdminUserDO::getId);
        }
        Set<Long> userIds = new LinkedHashSet<>();
        Set<Long> directUserIds = targetList.stream()
                .filter(item -> Objects.equals(item.getTargetType(), PartyFileTargetTypeEnum.USER.getType()))
                .map(PartyFileTargetDO::getTargetId)
                .collect(Collectors.toSet());
        if (CollUtil.isNotEmpty(directUserIds)) {
            userIds.addAll(directUserIds);
        }
        Set<Long> deptIds = targetList.stream()
                .filter(item -> Objects.equals(item.getTargetType(), PartyFileTargetTypeEnum.DEPT.getType()))
                .map(PartyFileTargetDO::getTargetId)
                .collect(Collectors.toSet());
        if (CollUtil.isNotEmpty(deptIds)) {
            Set<Long> allDeptIds = new LinkedHashSet<>(deptIds);
            deptIds.forEach(deptId -> allDeptIds.addAll(deptService.getChildDeptIdListFromCache(deptId)));
            userIds.addAll(CollectionUtils.convertSet(adminUserService.getUserListByDeptIds(allDeptIds), AdminUserDO::getId));
        }
        Set<Long> roleIds = targetList.stream()
                .filter(item -> Objects.equals(item.getTargetType(), PartyFileTargetTypeEnum.ROLE.getType()))
                .map(PartyFileTargetDO::getTargetId)
                .collect(Collectors.toSet());
        if (CollUtil.isNotEmpty(roleIds)) {
            userIds.addAll(permissionService.getUserRoleIdListByRoleId(roleIds));
        }
        return userIds;
    }

    private List<PartyFileAttachmentRespVO> buildAttachments(String attachmentFileIds) {
        List<Long> fileIds = parseFileIds(attachmentFileIds);
        if (fileIds.isEmpty()) {
            return Collections.emptyList();
        }
        List<PartyFileAttachmentRespVO> result = new ArrayList<>();
        for (Long fileId : fileIds) {
            FileDO file = partyFileAttachmentService.getFile(fileId);
            if (file == null) {
                continue;
            }
            PartyFileAttachmentRespVO respVO = new PartyFileAttachmentRespVO();
            respVO.setId(file.getId());
            respVO.setName(file.getName());
            respVO.setUrl(file.getUrl());
            respVO.setType(file.getType());
            respVO.setSize(file.getSize());
            result.add(respVO);
        }
        return result;
    }

    private void validateAttachmentAccessible(PartyFileDO partyFile, Long fileId) {
        List<Long> attachmentIds = parseFileIds(partyFile.getAttachmentFileIds());
        if (!attachmentIds.contains(fileId)) {
            throw exception(PARTY_FILE_ATTACHMENT_NOT_FOUND);
        }
    }

    private List<Long> parseFileIds(String attachmentFileIds) {
        if (StrUtil.isBlank(attachmentFileIds)) {
            return Collections.emptyList();
        }
        return StrUtil.splitTrim(attachmentFileIds, ',').stream()
                .filter(StrUtil::isNotBlank)
                .map(Long::valueOf)
                .collect(Collectors.toList());
    }

    private List<PartyFileTargetRespVO> buildTargetRespList(List<PartyFileTargetDO> targetList) {
        Set<Long> userIds = new LinkedHashSet<>();
        Set<Long> deptIds = new LinkedHashSet<>();
        Set<Long> roleIds = new LinkedHashSet<>();
        for (PartyFileTargetDO target : targetList) {
            if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.USER.getType())) {
                userIds.add(target.getTargetId());
            } else if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.DEPT.getType())) {
                deptIds.add(target.getTargetId());
            } else if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.ROLE.getType())) {
                roleIds.add(target.getTargetId());
            }
        }
        Map<Long, String> userNameMap = CollectionUtils.convertMap(adminUserService.getUserList(userIds), AdminUserDO::getId, AdminUserDO::getNickname);
        Map<Long, String> deptNameMap = CollectionUtils.convertMap(deptService.getDeptList(deptIds), DeptDO::getId, DeptDO::getName);
        Map<Long, String> roleNameMap = CollectionUtils.convertMap(roleService.getRoleList(roleIds), RoleDO::getId, RoleDO::getName);
        return targetList.stream().map(target -> {
            PartyFileTargetRespVO respVO = new PartyFileTargetRespVO();
            respVO.setTargetType(target.getTargetType());
            respVO.setTargetId(target.getTargetId());
            if (Objects.equals(target.getTargetType(), PartyFileTargetTypeEnum.ALL.getType())) {
                respVO.setTargetName("全员");
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

    private List<PartyFileReadRespVO> buildReadRespList(List<PartyFileReadDO> readList, List<AdminUserDO> users, Map<Long, DeptDO> deptMap) {
        Map<Long, AdminUserDO> userMap = CollectionUtils.convertMap(users, AdminUserDO::getId, Function.identity());
        return readList.stream().map(item -> {
            PartyFileReadRespVO respVO = new PartyFileReadRespVO();
            respVO.setUserId(item.getUserId());
            respVO.setUserNickname(item.getUserNickname());
            respVO.setReadTime(item.getReadTime());
            respVO.setReadSource(item.getReadSource());
            AdminUserDO user = userMap.get(item.getUserId());
            if (user != null) {
                respVO.setDeptId(user.getDeptId());
                DeptDO dept = deptMap.get(user.getDeptId());
                respVO.setDeptName(dept == null ? null : dept.getName());
            }
            return respVO;
        }).collect(Collectors.toList());
    }

    private List<PartyFileUnreadRespVO> buildUnreadRespList(List<AdminUserDO> users, Map<Long, DeptDO> deptMap,
                                                            Map<Long, PartyFileReadDO> readMap) {
        return users.stream()
                .filter(user -> !readMap.containsKey(user.getId()))
                .map(user -> {
                    PartyFileUnreadRespVO respVO = new PartyFileUnreadRespVO();
                    respVO.setUserId(user.getId());
                    respVO.setUserNickname(user.getNickname());
                    respVO.setDeptId(user.getDeptId());
                    DeptDO dept = deptMap.get(user.getDeptId());
                    respVO.setDeptName(dept == null ? null : dept.getName());
                    return respVO;
                })
                .collect(Collectors.toList());
    }
}
