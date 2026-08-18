package cn.iocoder.yudao.module.bpm.service.oa;

import cn.hutool.core.date.LocalDateTimeUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.api.task.BpmProcessInstanceApi;
import cn.iocoder.yudao.module.bpm.api.task.dto.BpmProcessInstanceCreateReqDTO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAExpenseCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAExpensePageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAExpenseDO;
import cn.iocoder.yudao.module.bpm.dal.mysql.oa.BpmOAExpenseMapper;
import cn.iocoder.yudao.module.bpm.enums.task.BpmTaskStatusEnum;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.util.HashMap;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.bpm.enums.ErrorCodeConstants.OA_LEAVE_NOT_EXISTS;

/**
 * OA 报销申请 Service 实现类
 *
 * @author jason
 * @author 芋道源码
 */
@Service
@Validated
public class BpmOAExpenseServiceImpl implements BpmOAExpenseService {

    /**
     * OA 报销对应的流程定义 KEY
     */
    public static final String PROCESS_KEY = "oa_expense";

    @Resource
    private BpmOAExpenseMapper expenseMapper;

    @Resource
    private BpmProcessInstanceApi processInstanceApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createExpense(Long userId, BpmOAExpenseCreateReqVO createReqVO) {
        // 插入 OA 报销单
        long day = LocalDateTimeUtil.between(createReqVO.getStartTime(), createReqVO.getEndTime()).toDays();
        BpmOAExpenseDO expense = BeanUtils.toBean(createReqVO, BpmOAExpenseDO.class)
                .setUserId(userId).setDay(day).setStatus(BpmTaskStatusEnum.RUNNING.getStatus());
        expenseMapper.insert(expense);

        // 发起 BPM 流程
        Map<String, Object> processInstanceVariables = new HashMap<>();
        processInstanceVariables.put("day", day);
        String processInstanceId = processInstanceApi.createProcessInstance(userId,
                new BpmProcessInstanceCreateReqDTO().setProcessDefinitionKey(PROCESS_KEY)
                        .setVariables(processInstanceVariables).setBusinessKey(String.valueOf(expense.getId()))
                        .setStartUserSelectAssignees(createReqVO.getStartUserSelectAssignees()));

        // 将工作流的编号，更新到 OA 报销单中
        expenseMapper.updateById(new BpmOAExpenseDO().setId(expense.getId()).setProcessInstanceId(processInstanceId));
        return expense.getId();
    }

    @Override
    public void updateExpenseStatus(Long id, Integer status) {
        validateExpenseExists(id);
        expenseMapper.updateById(new BpmOAExpenseDO().setId(id).setStatus(status));
    }

    private void validateExpenseExists(Long id) {
        if (expenseMapper.selectById(id) == null) {
            throw exception(OA_LEAVE_NOT_EXISTS);
        }
    }

    @Override
    public BpmOAExpenseDO getExpense(Long id) {
        return expenseMapper.selectById(id);
    }

    @Override
    public PageResult<BpmOAExpenseDO> getExpensePage(Long userId, BpmOAExpensePageReqVO pageReqVO) {
        return expenseMapper.selectPage(userId, pageReqVO);
    }

}
