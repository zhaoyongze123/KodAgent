package cn.iocoder.yudao.module.system.service.meetingroom;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.room.MeetingRoomPageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.room.MeetingRoomSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingRoomDO;

import javax.validation.Valid;
import java.util.List;

public interface MeetingRoomService {

    Long createMeetingRoom(@Valid MeetingRoomSaveReqVO createReqVO);

    void updateMeetingRoom(@Valid MeetingRoomSaveReqVO updateReqVO);

    void deleteMeetingRoom(Long id);

    MeetingRoomDO getMeetingRoom(Long id);

    PageResult<MeetingRoomDO> getMeetingRoomPage(MeetingRoomPageReqVO pageReqVO);

    List<MeetingRoomDO> getEnableMeetingRoomList();

}
