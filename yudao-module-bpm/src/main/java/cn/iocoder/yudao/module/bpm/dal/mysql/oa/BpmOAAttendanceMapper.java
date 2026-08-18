package cn.iocoder.yudao.module.bpm.dal.mysql.oa;

import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAAttendancePageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAAttendanceDO;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import org.apache.ibatis.annotations.Mapper;

/**
 * 补卡申请 Mapper
 *
 * @author jason
 * @author 芋道源码
 */
@Mapper
public interface BpmOAAttendanceMapper extends BaseMapperX<BpmOAAttendanceDO> {

    default PageResult<BpmOAAttendanceDO> selectPage(Long userId, BpmOAAttendancePageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<BpmOAAttendanceDO>()
                .eqIfPresent(BpmOAAttendanceDO::getUserId, userId)
                .eqIfPresent(BpmOAAttendanceDO::getStatus, reqVO.getStatus())
                .eqIfPresent(BpmOAAttendanceDO::getType, reqVO.getType())
                .likeIfPresent(BpmOAAttendanceDO::getReason, reqVO.getReason())
                .betweenIfPresent(BpmOAAttendanceDO::getCreateTime, reqVO.getCreateTime())
                .orderByDesc(BpmOAAttendanceDO::getId));
    }

}
