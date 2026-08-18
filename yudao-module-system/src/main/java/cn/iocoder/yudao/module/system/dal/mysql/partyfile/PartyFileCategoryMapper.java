package cn.iocoder.yudao.module.system.dal.mysql.partyfile;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileCategoryDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.Collection;
import java.util.List;

@Mapper
public interface PartyFileCategoryMapper extends BaseMapperX<PartyFileCategoryDO> {

    default List<PartyFileCategoryDO> selectListByStatus(Integer status) {
        return selectList(new LambdaQueryWrapperX<PartyFileCategoryDO>()
                .eqIfPresent(PartyFileCategoryDO::getStatus, status)
                .orderByAsc(PartyFileCategoryDO::getSort, PartyFileCategoryDO::getId));
    }

    default PartyFileCategoryDO selectByParentIdAndName(Long parentId, String name) {
        return selectOne(new LambdaQueryWrapperX<PartyFileCategoryDO>()
                .eq(PartyFileCategoryDO::getParentId, parentId)
                .eq(PartyFileCategoryDO::getName, name));
    }

    default List<PartyFileCategoryDO> selectListByParentId(Collection<Long> parentIds) {
        return selectList(new LambdaQueryWrapperX<PartyFileCategoryDO>()
                .in(PartyFileCategoryDO::getParentId, parentIds));
    }
}
