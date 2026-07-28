package cn.iocoder.yudao.module.system.dal.mysql.notice;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.dal.dataobject.notice.NoticeTargetDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.Collection;
import java.util.List;

@Mapper
public interface NoticeTargetMapper extends BaseMapperX<NoticeTargetDO> {

    default List<NoticeTargetDO> selectListByNoticeId(Long noticeId) {
        return selectList(new LambdaQueryWrapperX<NoticeTargetDO>()
                .eq(NoticeTargetDO::getNoticeId, noticeId)
                .orderByAsc(NoticeTargetDO::getTargetType, NoticeTargetDO::getTargetId, NoticeTargetDO::getId));
    }

    default List<NoticeTargetDO> selectListByTarget(Integer targetType, Collection<Long> targetIds) {
        return selectList(new LambdaQueryWrapperX<NoticeTargetDO>()
                .eq(NoticeTargetDO::getTargetType, targetType)
                .inIfPresent(NoticeTargetDO::getTargetId, targetIds));
    }

    default List<NoticeTargetDO> selectListByTargetType(Integer targetType) {
        return selectList(new LambdaQueryWrapperX<NoticeTargetDO>()
                .eq(NoticeTargetDO::getTargetType, targetType));
    }

    default void deleteByNoticeId(Long noticeId) {
        delete(new LambdaQueryWrapperX<NoticeTargetDO>()
                .eq(NoticeTargetDO::getNoticeId, noticeId));
    }

    default void deleteByNoticeIds(Collection<Long> noticeIds) {
        delete(new LambdaQueryWrapperX<NoticeTargetDO>()
                .inIfPresent(NoticeTargetDO::getNoticeId, noticeIds));
    }
}
