package cn.iocoder.yudao.module.bpm.dal.mysql.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOutingPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAOutingDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface BpmOAOutingMapper extends BaseMapperX<BpmOAOutingDO> {

    default PageResult<BpmOAOutingDO> selectPage(Long userId, BpmOAOutingPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<BpmOAOutingDO>()
                .eqIfPresent(BpmOAOutingDO::getUserId, userId)
                .eqIfPresent(BpmOAOutingDO::getStatus, reqVO.getStatus())
                .eqIfPresent(BpmOAOutingDO::getType, reqVO.getType())
                .likeIfPresent(BpmOAOutingDO::getReason, reqVO.getReason())
                .betweenIfPresent(BpmOAOutingDO::getCreateTime, reqVO.getCreateTime())
                .orderByDesc(BpmOAOutingDO::getId));
    }

}
