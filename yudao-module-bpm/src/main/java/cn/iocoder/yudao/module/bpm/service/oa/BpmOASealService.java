package cn.iocoder.yudao.module.bpm.service.oa;


import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOASealCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOASealPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOASealDO;

import javax.validation.Valid;

/**
 * 用章申请 Service 接口
 *
 * @author jason
 * @author 芋道源码
 */
public interface BpmOASealService {

    /**
     * 创建用章申请
     *
     * @param userId 用户编号
     * @param createReqVO 创建信息
     * @return 编号
     */
    Long createSeal(Long userId, @Valid BpmOASealCreateReqVO createReqVO);

    /**
     * 更新用章申请的状态
     *
     * @param id 编号
     * @param status 结果
     */
    void updateSealStatus(Long id, Integer status);

    /**
     * 获得用章申请
     *
     * @param id 编号
     * @return 用章申请
     */
    BpmOASealDO getSeal(Long id);

    /**
     * 获得用章申请分页
     *
     * @param userId 用户编号
     * @param pageReqVO 分页查询
     * @return 用章申请分页
     */
    PageResult<BpmOASealDO> getSealPage(Long userId, BpmOASealPageReqVO pageReqVO);

}
