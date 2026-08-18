package cn.iocoder.yudao.module.system.dal.mysql.partyfile;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileMyPageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFilePageReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.Collection;

@Mapper
public interface PartyFileMapper extends BaseMapperX<PartyFileDO> {

    default PageResult<PartyFileDO> selectPage(PartyFilePageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<PartyFileDO>()
                .likeIfPresent(PartyFileDO::getTitle, reqVO.getTitle())
                .eqIfPresent(PartyFileDO::getCategoryId, reqVO.getCategoryId())
                .eqIfPresent(PartyFileDO::getStatus, reqVO.getStatus())
                .orderByDesc(PartyFileDO::getPublishTime, PartyFileDO::getId));
    }

    default PageResult<PartyFileDO> selectMyPage(PartyFileMyPageReqVO reqVO, Collection<Long> ids) {
        return selectPage(reqVO, new LambdaQueryWrapperX<PartyFileDO>()
                .inIfPresent(PartyFileDO::getId, ids)
                .likeIfPresent(PartyFileDO::getTitle, reqVO.getTitle())
                .eqIfPresent(PartyFileDO::getCategoryId, reqVO.getCategoryId())
                .eq(PartyFileDO::getStatus, 0)
                .orderByDesc(PartyFileDO::getPublishTime, PartyFileDO::getId));
    }

    default java.util.List<PartyFileDO> selectListByKodSourceId(Long kodSourceId) {
        return selectList(new LambdaQueryWrapperX<PartyFileDO>()
                .eq(PartyFileDO::getKodSourceId, kodSourceId));
    }
}
