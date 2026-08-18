package cn.iocoder.yudao.module.bpm.service.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.api.task.BpmProcessInstanceApi;
import cn.iocoder.yudao.module.bpm.api.task.dto.BpmProcessInstanceCreateReqDTO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOASealCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOASealPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOASealDO;
import cn.iocoder.yudao.module.bpm.dal.mysql.oa.BpmOASealMapper;
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
import java.util.Map;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.bpm.enums.ErrorCodeConstants.OA_SEAL_NOT_EXISTS;

/**
 * OA 用章申请 Service 实现类
 *
 * @author jason
 * @author 芋道源码
 */
@Service
@Validated
public class BpmOASealServiceImpl implements BpmOASealService {

    /**
     * OA 用章对应的流程定义 KEY
     */
    public static final String PROCESS_KEY = "oa_seal";

    @Resource
    private BpmOASealMapper sealMapper;

    @Resource
    private BpmProcessInstanceApi processInstanceApi;
    @Resource
    private AdminUserApi adminUserApi;
    @Resource
    private DeptApi deptApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createSeal(Long userId, BpmOASealCreateReqVO createReqVO) {
        AdminUserRespDTO user = adminUserApi.getUser(userId);
        DeptRespDTO dept = user != null && user.getDeptId() != null ? deptApi.getDept(user.getDeptId()) : null;
        // 插入 OA 用章单
        long day = 0L;
        BpmOASealDO seal = BeanUtils.toBean(createReqVO, BpmOASealDO.class)
                .setUserId(userId)
                .setApplicantName(user != null ? user.getNickname() : null)
                .setDeptId(user != null ? user.getDeptId() : null)
                .setDeptName(dept != null ? dept.getName() : null)
                .setAttachmentUrls(JsonUtils.toJsonString(createReqVO.getAttachmentUrls()))
                .setStartTime(createReqVO.getStartTime())
                .setEndTime(createReqVO.getStartTime())
                .setDay(day)
                .setStatus(BpmTaskStatusEnum.RUNNING.getStatus());
        sealMapper.insert(seal);

        // 发起 BPM 流程
        Map<String, Object> processInstanceVariables = new HashMap<>();
        processInstanceVariables.put("day", day);
        processInstanceVariables.put("externalCarry", Boolean.TRUE.equals(createReqVO.getExternalCarry()));
        processInstanceVariables.put("fileCount", createReqVO.getFileCount());
        String processInstanceId = processInstanceApi.createProcessInstance(userId,
                new BpmProcessInstanceCreateReqDTO().setProcessDefinitionKey(PROCESS_KEY)
                        .setVariables(processInstanceVariables).setBusinessKey(String.valueOf(seal.getId()))
                        .setStartUserSelectAssignees(createReqVO.getStartUserSelectAssignees()));

        // 将工作流的编号，更新到 OA 用章单中
        sealMapper.updateById(new BpmOASealDO().setId(seal.getId()).setProcessInstanceId(processInstanceId));
        return seal.getId();
    }

    @Override
    public void updateSealStatus(Long id, Integer status) {
        validateSealExists(id);
        sealMapper.updateById(new BpmOASealDO().setId(id).setStatus(status));
    }

    private void validateSealExists(Long id) {
        if (sealMapper.selectById(id) == null) {
            throw exception(OA_SEAL_NOT_EXISTS);
        }
    }

    @Override
    public BpmOASealDO getSeal(Long id) {
        return sealMapper.selectById(id);
    }

    @Override
    public PageResult<BpmOASealDO> getSealPage(Long userId, BpmOASealPageReqVO pageReqVO) {
        return sealMapper.selectPage(userId, pageReqVO);
    }

}
