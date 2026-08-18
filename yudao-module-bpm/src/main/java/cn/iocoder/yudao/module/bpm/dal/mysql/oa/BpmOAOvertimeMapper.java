package cn.iocoder.yudao.module.bpm.dal.mysql.oa;

import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOvertimePageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAOvertimeDO;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import org.apache.ibatis.annotations.Mapper;

/**
 * 加班申请 Mapper
 *
 * @author jason
 * @author 芋道源码
 */
@Mapper
public interface BpmOAOvertimeMapper extends BaseMapperX<BpmOAOvertimeDO> {

    default PageResult<BpmOAOvertimeDO> selectPage(Long userId, BpmOAOvertimePageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<BpmOAOvertimeDO>()
                .eqIfPresent(BpmOAOvertimeDO::getUserId, userId)
                .eqIfPresent(BpmOAOvertimeDO::getStatus, reqVO.getStatus())
                .eqIfPresent(BpmOAOvertimeDO::getType, reqVO.getType())
                .likeIfPresent(BpmOAOvertimeDO::getReason, reqVO.getReason())
                .betweenIfPresent(BpmOAOvertimeDO::getCreateTime, reqVO.getCreateTime())
                .orderByDesc(BpmOAOvertimeDO::getId));
    }

}
