package cn.iocoder.yudao.module.system.dal.mysql.partyfile;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileTargetDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.Collection;
import java.util.List;

@Mapper
public interface PartyFileTargetMapper extends BaseMapperX<PartyFileTargetDO> {

    default List<PartyFileTargetDO> selectListByPartyFileId(Long partyFileId) {
        return selectList(new LambdaQueryWrapperX<PartyFileTargetDO>()
                .eq(PartyFileTargetDO::getPartyFileId, partyFileId)
                .orderByAsc(PartyFileTargetDO::getTargetType, PartyFileTargetDO::getTargetId, PartyFileTargetDO::getId));
    }

    default List<PartyFileTargetDO> selectListByPartyFileIds(Collection<Long> partyFileIds) {
        return selectList(new LambdaQueryWrapperX<PartyFileTargetDO>()
                .inIfPresent(PartyFileTargetDO::getPartyFileId, partyFileIds));
    }

    default List<PartyFileTargetDO> selectListByTarget(Integer targetType, Collection<Long> targetIds) {
        return selectList(new LambdaQueryWrapperX<PartyFileTargetDO>()
                .eq(PartyFileTargetDO::getTargetType, targetType)
                .inIfPresent(PartyFileTargetDO::getTargetId, targetIds));
    }

    default List<PartyFileTargetDO> selectListByTargetType(Integer targetType) {
        return selectList(new LambdaQueryWrapperX<PartyFileTargetDO>()
                .eq(PartyFileTargetDO::getTargetType, targetType));
    }

    default void deleteByPartyFileId(Long partyFileId) {
        delete(new LambdaQueryWrapperX<PartyFileTargetDO>()
                .eq(PartyFileTargetDO::getPartyFileId, partyFileId));
    }

    default void deleteByPartyFileIds(Collection<Long> partyFileIds) {
        delete(new LambdaQueryWrapperX<PartyFileTargetDO>()
                .inIfPresent(PartyFileTargetDO::getPartyFileId, partyFileIds));
    }
}
