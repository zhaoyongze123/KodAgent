package cn.iocoder.yudao.module.bpm.service.oa;


import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOATripCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOATripPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOATripDO;

import javax.validation.Valid;

/**
 * 出差申请 Service 接口
 *
 * @author jason
 * @author 芋道源码
 */
public interface BpmOATripService {

    /**
     * 创建出差申请
     *
     * @param userId 用户编号
     * @param createReqVO 创建信息
     * @return 编号
     */
    Long createTrip(Long userId, @Valid BpmOATripCreateReqVO createReqVO);

    /**
     * 更新出差申请的状态
     *
     * @param id 编号
     * @param status 结果
     */
    void updateTripStatus(Long id, Integer status);

    /**
     * 获得出差申请
     *
     * @param id 编号
     * @return 出差申请
     */
    BpmOATripDO getTrip(Long id);

    /**
     * 获得出差申请分页
     *
     * @param userId 用户编号
     * @param pageReqVO 分页查询
     * @return 出差申请分页
     */
    PageResult<BpmOATripDO> getTripPage(Long userId, BpmOATripPageReqVO pageReqVO);

}
