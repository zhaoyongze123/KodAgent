package cn.iocoder.yudao.module.system.dal.mysql.partyfile;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileReadDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.Collection;
import java.util.List;

@Mapper
public interface PartyFileReadMapper extends BaseMapperX<PartyFileReadDO> {

    default PartyFileReadDO selectByPartyFileIdAndUserId(Long partyFileId, Long userId) {
        return selectOne(new LambdaQueryWrapperX<PartyFileReadDO>()
                .eq(PartyFileReadDO::getPartyFileId, partyFileId)
                .eq(PartyFileReadDO::getUserId, userId));
    }

    default List<PartyFileReadDO> selectListByPartyFileId(Long partyFileId) {
        return selectList(new LambdaQueryWrapperX<PartyFileReadDO>()
                .eq(PartyFileReadDO::getPartyFileId, partyFileId)
                .orderByDesc(PartyFileReadDO::getReadTime, PartyFileReadDO::getId));
    }

    default List<PartyFileReadDO> selectListByPartyFileIdsAndUserId(Collection<Long> partyFileIds, Long userId) {
        return selectList(new LambdaQueryWrapperX<PartyFileReadDO>()
                .inIfPresent(PartyFileReadDO::getPartyFileId, partyFileIds)
                .eq(PartyFileReadDO::getUserId, userId));
    }

    default void deleteByPartyFileId(Long partyFileId) {
        delete(new LambdaQueryWrapperX<PartyFileReadDO>()
                .eq(PartyFileReadDO::getPartyFileId, partyFileId));
    }

    default void deleteByPartyFileIds(Collection<Long> partyFileIds) {
        delete(new LambdaQueryWrapperX<PartyFileReadDO>()
                .inIfPresent(PartyFileReadDO::getPartyFileId, partyFileIds));
    }
}
