package cn.iocoder.yudao.module.bpm.service.oa;


import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAExpenseCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAExpensePageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAExpenseDO;

import javax.validation.Valid;

/**
 * 报销申请 Service 接口
 *
 * @author jason
 * @author 芋道源码
 */
public interface BpmOAExpenseService {

    /**
     * 创建报销申请
     *
     * @param userId 用户编号
     * @param createReqVO 创建信息
     * @return 编号
     */
    Long createExpense(Long userId, @Valid BpmOAExpenseCreateReqVO createReqVO);

    /**
     * 更新报销申请的状态
     *
     * @param id 编号
     * @param status 结果
     */
    void updateExpenseStatus(Long id, Integer status);

    /**
     * 获得报销申请
     *
     * @param id 编号
     * @return 报销申请
     */
    BpmOAExpenseDO getExpense(Long id);

    /**
     * 获得报销申请分页
     *
     * @param userId 用户编号
     * @param pageReqVO 分页查询
     * @return 报销申请分页
     */
    PageResult<BpmOAExpenseDO> getExpensePage(Long userId, BpmOAExpensePageReqVO pageReqVO);

}
