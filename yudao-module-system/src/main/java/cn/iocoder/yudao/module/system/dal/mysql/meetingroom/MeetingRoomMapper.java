package cn.iocoder.yudao.module.system.dal.mysql.meetingroom;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.room.MeetingRoomPageReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingRoomDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface MeetingRoomMapper extends BaseMapperX<MeetingRoomDO> {

    default PageResult<MeetingRoomDO> selectPage(MeetingRoomPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<MeetingRoomDO>()
                .likeIfPresent(MeetingRoomDO::getName, reqVO.getName())
                .likeIfPresent(MeetingRoomDO::getLocation, reqVO.getLocation())
                .eqIfPresent(MeetingRoomDO::getStatus, reqVO.getStatus())
                .orderByAsc(MeetingRoomDO::getSort)
                .orderByDesc(MeetingRoomDO::getId));
    }

    default MeetingRoomDO selectByName(String name) {
        return selectOne(MeetingRoomDO::getName, name);
    }

    default List<MeetingRoomDO> selectEnableList() {
        return selectList(new LambdaQueryWrapperX<MeetingRoomDO>()
                .eq(MeetingRoomDO::getStatus, 0)
                .orderByAsc(MeetingRoomDO::getSort)
                .orderByDesc(MeetingRoomDO::getId));
    }

}
