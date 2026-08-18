package cn.iocoder.yudao.module.bpm.dal.mysql.oa;

import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOASealPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOASealDO;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import org.apache.ibatis.annotations.Mapper;

/**
 * 用章申请 Mapper
 *
 * @author jason
 * @author 芋道源码
 */
@Mapper
public interface BpmOASealMapper extends BaseMapperX<BpmOASealDO> {

    default PageResult<BpmOASealDO> selectPage(Long userId, BpmOASealPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<BpmOASealDO>()
                .eqIfPresent(BpmOASealDO::getUserId, userId)
                .eqIfPresent(BpmOASealDO::getStatus, reqVO.getStatus())
                .eqIfPresent(BpmOASealDO::getType, reqVO.getType())
                .likeIfPresent(BpmOASealDO::getFileName, reqVO.getFileName())
                .likeIfPresent(BpmOASealDO::getReason, reqVO.getReason())
                .likeIfPresent(BpmOASealDO::getCounterpartUnit, reqVO.getCounterpartUnit())
                .betweenIfPresent(BpmOASealDO::getCreateTime, reqVO.getCreateTime())
                .orderByDesc(BpmOASealDO::getId));
    }

}
