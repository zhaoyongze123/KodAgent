package cn.iocoder.yudao.module.bpm.service.oa;


import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOvertimeCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOvertimePageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAOvertimeDO;

import javax.validation.Valid;

/**
 * 加班申请 Service 接口
 *
 * @author jason
 * @author 芋道源码
 */
public interface BpmOAOvertimeService {

    /**
     * 创建加班申请
     *
     * @param userId 用户编号
     * @param createReqVO 创建信息
     * @return 编号
     */
    Long createOvertime(Long userId, @Valid BpmOAOvertimeCreateReqVO createReqVO);

    /**
     * 更新加班申请的状态
     *
     * @param id 编号
     * @param status 结果
     */
    void updateOvertimeStatus(Long id, Integer status);

    /**
     * 获得加班申请
     *
     * @param id 编号
     * @return 加班申请
     */
    BpmOAOvertimeDO getOvertime(Long id);

    /**
     * 获得加班申请分页
     *
     * @param userId 用户编号
     * @param pageReqVO 分页查询
     * @return 加班申请分页
     */
    PageResult<BpmOAOvertimeDO> getOvertimePage(Long userId, BpmOAOvertimePageReqVO pageReqVO);

}
