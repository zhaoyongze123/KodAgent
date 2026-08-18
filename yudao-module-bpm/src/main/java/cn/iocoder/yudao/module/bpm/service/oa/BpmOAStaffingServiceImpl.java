package cn.iocoder.yudao.module.bpm.service.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.module.bpm.api.task.BpmProcessInstanceApi;
import cn.iocoder.yudao.module.bpm.api.task.dto.BpmProcessInstanceCreateReqDTO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAStaffingCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAStaffingPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAStaffingDO;
import cn.iocoder.yudao.module.bpm.dal.mysql.oa.BpmOAStaffingMapper;
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
import static cn.iocoder.yudao.module.bpm.enums.ErrorCodeConstants.OA_STAFFING_NOT_EXISTS;

@Service
@Validated
public class BpmOAStaffingServiceImpl implements BpmOAStaffingService {

    public static final String PROCESS_KEY = "oa_staffing";

    @Resource
    private BpmOAStaffingMapper staffingMapper;
    @Resource
    private BpmProcessInstanceApi processInstanceApi;
    @Resource
    private AdminUserApi adminUserApi;
    @Resource
    private DeptApi deptApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createStaffing(Long userId, BpmOAStaffingCreateReqVO createReqVO) {
        AdminUserRespDTO user = adminUserApi.getUser(userId);
        DeptRespDTO dept = user != null && user.getDeptId() != null ? deptApi.getDept(user.getDeptId()) : null;
        List<Long> memberIds = createReqVO.getMemberIds();
        Map<Long, AdminUserRespDTO> memberMap = adminUserApi.getUserMap(memberIds);
        String memberNames = memberIds.stream()
                .map(memberMap::get)
                .filter(Objects::nonNull)
                .map(AdminUserRespDTO::getNickname)
                .collect(Collectors.joining("、"));
        BpmOAStaffingDO staffing = BpmOAStaffingDO.builder()
                .userId(userId)
                .applicantName(user != null ? user.getNickname() : null)
                .deptId(user != null ? user.getDeptId() : null)
                .deptName(dept != null ? dept.getName() : null)
                .projectName(createReqVO.getProjectName())
                .memberIds(JsonUtils.toJsonString(memberIds))
                .memberNames(memberNames)
                .reason(createReqVO.getReason())
                .transferTime(createReqVO.getTransferTime())
                .expectedWorkPeriod(createReqVO.getExpectedWorkPeriod())
                .targetUnit(createReqVO.getTargetUnit())
                .remark(createReqVO.getRemark())
                .status(BpmTaskStatusEnum.RUNNING.getStatus())
                .build();
        staffingMapper.insert(staffing);

        Map<String, Object> processInstanceVariables = new HashMap<>();
        processInstanceVariables.put("memberCount", memberIds.size());
        String processInstanceId = processInstanceApi.createProcessInstance(userId,
                new BpmProcessInstanceCreateReqDTO().setProcessDefinitionKey(PROCESS_KEY)
                        .setVariables(processInstanceVariables).setBusinessKey(String.valueOf(staffing.getId()))
                        .setStartUserSelectAssignees(createReqVO.getStartUserSelectAssignees()));
        staffingMapper.updateById(new BpmOAStaffingDO().setId(staffing.getId()).setProcessInstanceId(processInstanceId));
        return staffing.getId();
    }

    @Override
    public void updateStaffingStatus(Long id, Integer status) {
        validateStaffingExists(id);
        staffingMapper.updateById(new BpmOAStaffingDO().setId(id).setStatus(status));
    }

    private void validateStaffingExists(Long id) {
        if (staffingMapper.selectById(id) == null) {
            throw exception(OA_STAFFING_NOT_EXISTS);
        }
    }

    @Override
    public BpmOAStaffingDO getStaffing(Long id) {
        return staffingMapper.selectById(id);
    }

    @Override
    public PageResult<BpmOAStaffingDO> getStaffingPage(Long userId, BpmOAStaffingPageReqVO pageReqVO) {
        return staffingMapper.selectPage(userId, pageReqVO);
    }

}
