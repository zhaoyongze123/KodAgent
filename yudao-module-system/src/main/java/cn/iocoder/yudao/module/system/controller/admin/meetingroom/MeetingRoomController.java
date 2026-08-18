package cn.iocoder.yudao.module.system.controller.admin.meetingroom;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.room.*;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingRoomDO;
import cn.iocoder.yudao.module.system.service.meetingroom.MeetingRoomService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.validation.Valid;
import java.util.List;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - 会议室")
@RestController
@RequestMapping("/system/meeting-room")
@Validated
public class MeetingRoomController {

    @Resource
    private MeetingRoomService meetingRoomService;

    @PostMapping("/create")
    @Operation(summary = "新增会议室")
    @PreAuthorize("@ss.hasPermission('system:meeting-room:create')")
    public CommonResult<Long> createMeetingRoom(@Valid @RequestBody MeetingRoomSaveReqVO createReqVO) {
        return success(meetingRoomService.createMeetingRoom(createReqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "修改会议室")
    @PreAuthorize("@ss.hasPermission('system:meeting-room:update')")
    public CommonResult<Boolean> updateMeetingRoom(@Valid @RequestBody MeetingRoomSaveReqVO updateReqVO) {
        meetingRoomService.updateMeetingRoom(updateReqVO);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除会议室")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    @PreAuthorize("@ss.hasPermission('system:meeting-room:delete')")
    public CommonResult<Boolean> deleteMeetingRoom(@RequestParam("id") Long id) {
        meetingRoomService.deleteMeetingRoom(id);
        return success(true);
    }

    @GetMapping("/get")
    @Operation(summary = "获得会议室")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    @PreAuthorize("@ss.hasPermission('system:meeting-room:query')")
    public CommonResult<MeetingRoomRespVO> getMeetingRoom(@RequestParam("id") Long id) {
        MeetingRoomDO room = meetingRoomService.getMeetingRoom(id);
        return success(BeanUtils.toBean(room, MeetingRoomRespVO.class));
    }

    @GetMapping("/page")
    @Operation(summary = "获得会议室分页")
    @PreAuthorize("@ss.hasPermission('system:meeting-room:query')")
    public CommonResult<PageResult<MeetingRoomRespVO>> getMeetingRoomPage(@Valid MeetingRoomPageReqVO pageReqVO) {
        PageResult<MeetingRoomDO> pageResult = meetingRoomService.getMeetingRoomPage(pageReqVO);
        return success(BeanUtils.toBean(pageResult, MeetingRoomRespVO.class));
    }

    @GetMapping("/simple-list")
    @Operation(summary = "获得启用中的会议室精简列表")
    public CommonResult<List<MeetingRoomSimpleRespVO>> getEnableMeetingRoomList() {
        return success(meetingRoomService.getEnableMeetingRoomList().stream()
                .map(item -> new MeetingRoomSimpleRespVO(item.getId(), item.getName(), item.getLocation()))
                .collect(Collectors.toList()));
    }

}
