package cn.iocoder.yudao.module.bpm.service.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.module.bpm.api.task.BpmProcessInstanceApi;
import cn.iocoder.yudao.module.bpm.api.task.dto.BpmProcessInstanceCreateReqDTO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAProjectCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAProjectPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAProjectDO;
import cn.iocoder.yudao.module.bpm.dal.mysql.oa.BpmOAProjectMapper;
import cn.iocoder.yudao.module.bpm.enums.task.BpmTaskStatusEnum;
import cn.iocoder.yudao.module.system.api.dept.DeptApi;
import cn.iocoder.yudao.module.system.api.dept.dto.DeptRespDTO;
import cn.iocoder.yudao.module.system.api.user.AdminUserApi;
import cn.iocoder.yudao.module.system.api.user.dto.AdminUserRespDTO;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.bpm.enums.ErrorCodeConstants.OA_PROJECT_NOT_EXISTS;

@Service
@Validated
public class BpmOAProjectServiceImpl implements BpmOAProjectService {

    public static final String PROCESS_KEY = "oa_project";

    @Resource
    private BpmOAProjectMapper projectMapper;
    @Resource
    private BpmProcessInstanceApi processInstanceApi;
    @Resource
    private AdminUserApi adminUserApi;
    @Resource
    private DeptApi deptApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createProject(Long userId, BpmOAProjectCreateReqVO createReqVO) {
        AdminUserRespDTO user = adminUserApi.getUser(userId);
        DeptRespDTO dept = user != null && user.getDeptId() != null ? deptApi.getDept(user.getDeptId()) : null;
        AdminUserRespDTO leader = adminUserApi.getUser(createReqVO.getProjectLeaderId());
        List<Long> participantDeptIds = createReqVO.getParticipantDeptIds();
        Map<Long, DeptRespDTO> participantDeptMap = deptApi.getDeptMap(participantDeptIds);
        String participantDeptNames = participantDeptIds == null ? null : participantDeptIds.stream()
                .map(participantDeptMap::get)
                .filter(Objects::nonNull)
                .map(DeptRespDTO::getName)
                .collect(Collectors.joining("、"));

        BpmOAProjectDO project = BpmOAProjectDO.builder()
                .userId(userId)
                .applicantName(user != null ? user.getNickname() : null)
                .deptId(user != null ? user.getDeptId() : null)
                .deptName(dept != null ? dept.getName() : null)
                .projectName(createReqVO.getProjectName())
                .projectType(createReqVO.getProjectType())
                .ownerUnit(createReqVO.getOwnerUnit())
                .projectSource(createReqVO.getProjectSource())
                .projectLeaderId(createReqVO.getProjectLeaderId())
                .projectLeaderName(leader != null ? leader.getNickname() : null)
                .projectOverview(createReqVO.getProjectOverview())
                .projectAmount(createReqVO.getProjectAmount())
                .plannedStartTime(createReqVO.getPlannedStartTime())
                .plannedEndTime(createReqVO.getPlannedEndTime())
                .participantDeptIds(JsonUtils.toJsonString(participantDeptIds))
                .participantDeptNames(participantDeptNames)
                .riskDescription(createReqVO.getRiskDescription())
                .attachmentUrls(JsonUtils.toJsonString(createReqVO.getAttachmentUrls()))
                .remark(createReqVO.getRemark())
                .status(BpmTaskStatusEnum.RUNNING.getStatus())
                .build();
        projectMapper.insert(project);

        Map<String, Object> processInstanceVariables = new HashMap<>();
        processInstanceVariables.put("projectAmount", createReqVO.getProjectAmount());
        String processInstanceId = processInstanceApi.createProcessInstance(userId,
                new BpmProcessInstanceCreateReqDTO().setProcessDefinitionKey(PROCESS_KEY)
                        .setVariables(processInstanceVariables).setBusinessKey(String.valueOf(project.getId()))
                        .setStartUserSelectAssignees(createReqVO.getStartUserSelectAssignees()));
        projectMapper.updateById(new BpmOAProjectDO().setId(project.getId()).setProcessInstanceId(processInstanceId));
        return project.getId();
    }

    @Override
    public void updateProjectStatus(Long id, Integer status) {
        validateProjectExists(id);
        projectMapper.updateById(new BpmOAProjectDO().setId(id).setStatus(status));
    }

    private void validateProjectExists(Long id) {
        if (projectMapper.selectById(id) == null) {
            throw exception(OA_PROJECT_NOT_EXISTS);
        }
    }

    @Override
    public BpmOAProjectDO getProject(Long id) {
        return projectMapper.selectById(id);
    }

    @Override
    public PageResult<BpmOAProjectDO> getProjectPage(Long userId, BpmOAProjectPageReqVO pageReqVO) {
        return projectMapper.selectPage(userId, pageReqVO);
    }

}
