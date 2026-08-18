package cn.iocoder.yudao.module.bpm.dal.mysql.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAStaffingPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAStaffingDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface BpmOAStaffingMapper extends BaseMapperX<BpmOAStaffingDO> {

    default PageResult<BpmOAStaffingDO> selectPage(Long userId, BpmOAStaffingPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<BpmOAStaffingDO>()
                .eqIfPresent(BpmOAStaffingDO::getUserId, userId)
                .eqIfPresent(BpmOAStaffingDO::getStatus, reqVO.getStatus())
                .likeIfPresent(BpmOAStaffingDO::getProjectName, reqVO.getProjectName())
                .likeIfPresent(BpmOAStaffingDO::getReason, reqVO.getReason())
                .likeIfPresent(BpmOAStaffingDO::getTargetUnit, reqVO.getTargetUnit())
                .betweenIfPresent(BpmOAStaffingDO::getCreateTime, reqVO.getCreateTime())
                .orderByDesc(BpmOAStaffingDO::getId));
    }

}
