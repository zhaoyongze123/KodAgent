package cn.iocoder.yudao.module.system.dal.mysql.notice;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.dal.dataobject.notice.NoticeReadDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface NoticeReadMapper extends BaseMapperX<NoticeReadDO> {

    default NoticeReadDO selectByNoticeIdAndUserId(Long noticeId, Long userId) {
        return selectOne(new LambdaQueryWrapperX<NoticeReadDO>()
                .eq(NoticeReadDO::getNoticeId, noticeId)
                .eq(NoticeReadDO::getUserId, userId));
    }

    default List<NoticeReadDO> selectListByNoticeId(Long noticeId) {
        return selectList(new LambdaQueryWrapperX<NoticeReadDO>()
                .eq(NoticeReadDO::getNoticeId, noticeId)
                .orderByDesc(NoticeReadDO::getReadTime, NoticeReadDO::getId));
    }
}
