package cn.iocoder.yudao.module.system.service.meetingroom;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.room.MeetingRoomPageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.room.MeetingRoomSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingRoomDO;
import cn.iocoder.yudao.module.system.dal.mysql.meetingroom.MeetingRoomMapper;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.util.List;
import java.util.Objects;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.MEETING_ROOM_NAME_DUPLICATE;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.MEETING_ROOM_NOT_EXISTS;

@Service
@Validated
public class MeetingRoomServiceImpl implements MeetingRoomService {

    @Resource
    private MeetingRoomMapper meetingRoomMapper;

    @Override
    public Long createMeetingRoom(MeetingRoomSaveReqVO createReqVO) {
        validateMeetingRoomNameUnique(null, createReqVO.getName());
        MeetingRoomDO room = BeanUtils.toBean(createReqVO, MeetingRoomDO.class);
        meetingRoomMapper.insert(room);
        return room.getId();
    }

    @Override
    public void updateMeetingRoom(MeetingRoomSaveReqVO updateReqVO) {
        validateMeetingRoomExists(updateReqVO.getId());
        validateMeetingRoomNameUnique(updateReqVO.getId(), updateReqVO.getName());
        meetingRoomMapper.updateById(BeanUtils.toBean(updateReqVO, MeetingRoomDO.class));
    }

    @Override
    public void deleteMeetingRoom(Long id) {
        validateMeetingRoomExists(id);
        meetingRoomMapper.deleteById(id);
    }

    @Override
    public MeetingRoomDO getMeetingRoom(Long id) {
        return meetingRoomMapper.selectById(id);
    }

    @Override
    public PageResult<MeetingRoomDO> getMeetingRoomPage(MeetingRoomPageReqVO pageReqVO) {
        return meetingRoomMapper.selectPage(pageReqVO);
    }

    @Override
    public List<MeetingRoomDO> getEnableMeetingRoomList() {
        return meetingRoomMapper.selectEnableList();
    }

    private void validateMeetingRoomExists(Long id) {
        if (meetingRoomMapper.selectById(id) == null) {
            throw exception(MEETING_ROOM_NOT_EXISTS);
        }
    }

    private void validateMeetingRoomNameUnique(Long id, String name) {
        MeetingRoomDO room = meetingRoomMapper.selectByName(name);
        if (room != null && !Objects.equals(room.getId(), id)) {
            throw exception(MEETING_ROOM_NAME_DUPLICATE, name);
        }
    }

}
