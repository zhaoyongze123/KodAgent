package cn.iocoder.yudao.module.bpm.dal.mysql.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOADocumentPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOADocumentDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface BpmOADocumentMapper extends BaseMapperX<BpmOADocumentDO> {

    default PageResult<BpmOADocumentDO> selectPage(Long userId, BpmOADocumentPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<BpmOADocumentDO>()
                .eqIfPresent(BpmOADocumentDO::getUserId, userId)
                .eqIfPresent(BpmOADocumentDO::getStatus, reqVO.getStatus())
                .likeIfPresent(BpmOADocumentDO::getFileType, reqVO.getFileType())
                .likeIfPresent(BpmOADocumentDO::getTitle, reqVO.getTitle())
                .likeIfPresent(BpmOADocumentDO::getRelatedProject, reqVO.getRelatedProject())
                .likeIfPresent(BpmOADocumentDO::getCounterpartUnit, reqVO.getCounterpartUnit())
                .betweenIfPresent(BpmOADocumentDO::getCreateTime, reqVO.getCreateTime())
                .orderByDesc(BpmOADocumentDO::getId));
    }

}
