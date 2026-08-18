package cn.iocoder.yudao.module.system.dal.mysql.auth;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.dal.dataobject.auth.KodSsoUserBindDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface KodSsoUserBindMapper extends BaseMapperX<KodSsoUserBindDO> {

    default KodSsoUserBindDO selectByKodUserId(String kodUserId) {
        return selectOne(KodSsoUserBindDO::getKodUserId, kodUserId);
    }

    default KodSsoUserBindDO selectByKodUsername(String kodUsername) {
        return selectOne(KodSsoUserBindDO::getKodUsername, kodUsername);
    }

    default void deleteByKodUserId(String kodUserId) {
        delete(new LambdaQueryWrapperX<KodSsoUserBindDO>()
                .eq(KodSsoUserBindDO::getKodUserId, kodUserId));
    }

    default KodSsoUserBindDO selectByUserId(Long userId) {
        return selectOne(KodSsoUserBindDO::getUserId, userId);
    }

    /**
     * SSO 成功后显式刷新用户令牌。
     *
     * 令牌字段使用加密 TypeHandler，不能依赖实体自动更新时的变更判断，
     * 否则在令牌已失效但实体字段比较结果不可靠时会继续保留旧令牌。
     */
    @Update("UPDATE system_kod_sso_user_bind "
            + "SET kod_access_token = #{kodAccessToken, "
            + "typeHandler=cn.iocoder.yudao.framework.mybatis.core.type.EncryptTypeHandler}, "
            + "update_time = NOW() "
            + "WHERE user_id = #{userId} AND deleted = 0")
    int updateKodAccessTokenByUserId(@Param("userId") Long userId,
                                     @Param("kodAccessToken") String kodAccessToken);

    default void deleteByUserId(Long userId) {
        delete(new LambdaQueryWrapperX<KodSsoUserBindDO>()
                .eq(KodSsoUserBindDO::getUserId, userId));
    }

}
