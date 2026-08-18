package cn.iocoder.yudao.module.bpm.service.oa;


import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAAttendanceCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAAttendancePageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAAttendanceDO;

import javax.validation.Valid;

/**
 * 补卡申请 Service 接口
 *
 * @author jason
 * @author 芋道源码
 */
public interface BpmOAAttendanceService {

    /**
     * 创建补卡申请
     *
     * @param userId 用户编号
     * @param createReqVO 创建信息
     * @return 编号
     */
    Long createAttendance(Long userId, @Valid BpmOAAttendanceCreateReqVO createReqVO);

    /**
     * 更新补卡申请的状态
     *
     * @param id 编号
     * @param status 结果
     */
    void updateAttendanceStatus(Long id, Integer status);

    /**
     * 获得补卡申请
     *
     * @param id 编号
     * @return 补卡申请
     */
    BpmOAAttendanceDO getAttendance(Long id);

    /**
     * 获得补卡申请分页
     *
     * @param userId 用户编号
     * @param pageReqVO 分页查询
     * @return 补卡申请分页
     */
    PageResult<BpmOAAttendanceDO> getAttendancePage(Long userId, BpmOAAttendancePageReqVO pageReqVO);

}
