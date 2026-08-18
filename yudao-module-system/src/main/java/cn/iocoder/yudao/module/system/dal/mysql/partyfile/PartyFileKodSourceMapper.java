package cn.iocoder.yudao.module.system.dal.mysql.partyfile;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource.PartyFileKodSourcePageReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileKodSourceDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface PartyFileKodSourceMapper extends BaseMapperX<PartyFileKodSourceDO> {

    default PageResult<PartyFileKodSourceDO> selectPage(PartyFileKodSourcePageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<PartyFileKodSourceDO>()
                .likeIfPresent(PartyFileKodSourceDO::getName, reqVO.getName())
                .eqIfPresent(PartyFileKodSourceDO::getStatus, reqVO.getStatus())
                .orderByDesc(PartyFileKodSourceDO::getIsDefault, PartyFileKodSourceDO::getId));
    }

    default PartyFileKodSourceDO selectByName(String name) {
        return selectOne(PartyFileKodSourceDO::getName, name);
    }

    default List<PartyFileKodSourceDO> selectEnabledList() {
        return selectList(new LambdaQueryWrapperX<PartyFileKodSourceDO>()
                .eq(PartyFileKodSourceDO::getStatus, 0)
                .orderByDesc(PartyFileKodSourceDO::getIsDefault, PartyFileKodSourceDO::getId));
    }

    default PartyFileKodSourceDO selectDefault() {
        return selectOne(PartyFileKodSourceDO::getIsDefault, true);
    }
}
