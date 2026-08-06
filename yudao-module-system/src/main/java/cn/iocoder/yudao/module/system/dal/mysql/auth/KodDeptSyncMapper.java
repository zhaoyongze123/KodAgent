package cn.iocoder.yudao.module.system.dal.mysql.auth;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.dal.dataobject.auth.KodDeptSyncDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface KodDeptSyncMapper extends BaseMapperX<KodDeptSyncDO> {

    default KodDeptSyncDO selectByKodGroupId(Long tenantId, String kodGroupId) {
        return selectOne(new LambdaQueryWrapperX<KodDeptSyncDO>()
                .eq(KodDeptSyncDO::getTenantId, tenantId)
                .eq(KodDeptSyncDO::getKodGroupId, kodGroupId));
    }

    default KodDeptSyncDO selectByLocalDeptId(Long tenantId, Long localDeptId) {
        return selectOne(new LambdaQueryWrapperX<KodDeptSyncDO>()
                .eq(KodDeptSyncDO::getTenantId, tenantId)
                .eq(KodDeptSyncDO::getLocalDeptId, localDeptId));
    }

    default List<KodDeptSyncDO> selectListByTenantId(Long tenantId) {
        return selectList(new LambdaQueryWrapperX<KodDeptSyncDO>()
                .eq(KodDeptSyncDO::getTenantId, tenantId)
                .orderByAsc(KodDeptSyncDO::getId));
    }
}
