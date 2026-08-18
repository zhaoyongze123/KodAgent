package cn.iocoder.yudao.module.bpm.dal.mysql.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOALeaveCancelPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOALeaveCancelDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface BpmOALeaveCancelMapper extends BaseMapperX<BpmOALeaveCancelDO> {

    default PageResult<BpmOALeaveCancelDO> selectPage(Long userId, BpmOALeaveCancelPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<BpmOALeaveCancelDO>()
                .eqIfPresent(BpmOALeaveCancelDO::getUserId, userId)
                .eqIfPresent(BpmOALeaveCancelDO::getStatus, reqVO.getStatus())
                .eqIfPresent(BpmOALeaveCancelDO::getType, reqVO.getType())
                .likeIfPresent(BpmOALeaveCancelDO::getReason, reqVO.getReason())
                .betweenIfPresent(BpmOALeaveCancelDO::getCreateTime, reqVO.getCreateTime())
                .orderByDesc(BpmOALeaveCancelDO::getId));
    }

}
