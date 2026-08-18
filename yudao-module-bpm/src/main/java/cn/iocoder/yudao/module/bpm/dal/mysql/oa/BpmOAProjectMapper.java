package cn.iocoder.yudao.module.bpm.dal.mysql.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAProjectPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAProjectDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface BpmOAProjectMapper extends BaseMapperX<BpmOAProjectDO> {

    default PageResult<BpmOAProjectDO> selectPage(Long userId, BpmOAProjectPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<BpmOAProjectDO>()
                .eqIfPresent(BpmOAProjectDO::getUserId, userId)
                .eqIfPresent(BpmOAProjectDO::getStatus, reqVO.getStatus())
                .likeIfPresent(BpmOAProjectDO::getProjectName, reqVO.getProjectName())
                .likeIfPresent(BpmOAProjectDO::getProjectType, reqVO.getProjectType())
                .likeIfPresent(BpmOAProjectDO::getOwnerUnit, reqVO.getOwnerUnit())
                .likeIfPresent(BpmOAProjectDO::getProjectLeaderName, reqVO.getProjectLeaderName())
                .betweenIfPresent(BpmOAProjectDO::getCreateTime, reqVO.getCreateTime())
                .orderByDesc(BpmOAProjectDO::getId));
    }

}
