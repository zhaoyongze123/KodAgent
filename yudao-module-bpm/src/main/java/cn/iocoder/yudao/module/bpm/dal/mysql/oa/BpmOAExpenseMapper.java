package cn.iocoder.yudao.module.bpm.dal.mysql.oa;

import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAExpensePageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAExpenseDO;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import org.apache.ibatis.annotations.Mapper;

/**
 * 报销申请 Mapper
 *
 * @author jason
 * @author 芋道源码
 */
@Mapper
public interface BpmOAExpenseMapper extends BaseMapperX<BpmOAExpenseDO> {

    default PageResult<BpmOAExpenseDO> selectPage(Long userId, BpmOAExpensePageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<BpmOAExpenseDO>()
                .eqIfPresent(BpmOAExpenseDO::getUserId, userId)
                .eqIfPresent(BpmOAExpenseDO::getStatus, reqVO.getStatus())
                .eqIfPresent(BpmOAExpenseDO::getType, reqVO.getType())
                .likeIfPresent(BpmOAExpenseDO::getReason, reqVO.getReason())
                .betweenIfPresent(BpmOAExpenseDO::getCreateTime, reqVO.getCreateTime())
                .orderByDesc(BpmOAExpenseDO::getId));
    }

}
