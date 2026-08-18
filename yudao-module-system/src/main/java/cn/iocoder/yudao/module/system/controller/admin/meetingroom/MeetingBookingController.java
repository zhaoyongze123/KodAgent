package cn.iocoder.yudao.module.system.controller.admin.meetingroom;

import cn.hutool.core.collection.CollUtil;
import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.framework.datapermission.core.util.DataPermissionUtils;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking.*;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingBookingDO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingRoomDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.service.meetingroom.MeetingBookingService;
import cn.iocoder.yudao.module.system.service.meetingroom.MeetingRoomService;
import cn.iocoder.yudao.module.system.service.permission.PermissionService;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.validation.Valid;
import java.util.*;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;

@Tag(name = "管理后台 - 会议室预定")
@RestController
@RequestMapping("/system/meeting-booking")
@Validated
public class MeetingBookingController {

    @Resource
    private MeetingBookingService meetingBookingService;
    @Resource
    private MeetingRoomService meetingRoomService;
    @Resource
    private AdminUserService adminUserService;
    @Resource
    private PermissionService permissionService;

    @PostMapping("/create")
    @Operation(summary = "创建会议室预定")
    public CommonResult<Long> createMeetingBooking(@Valid @RequestBody MeetingBookingSaveReqVO createReqVO) {
        return success(meetingBookingService.createMeetingBooking(getLoginUserId(), createReqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "管理员修改会议室预定")
    @PreAuthorize("@ss.hasPermission('system:meeting-booking:update')")
    public CommonResult<Boolean> updateMeetingBooking(@Valid @RequestBody MeetingBookingSaveReqVO updateReqVO) {
        meetingBookingService.updateMeetingBookingByAdmin(getLoginUserId(), updateReqVO);
        return success(true);
    }

    @PutMapping("/update-my")
    @Operation(summary = "员工修改本人未开始会议室预定")
    public CommonResult<Boolean> updateMyMeetingBooking(@Valid @RequestBody MeetingBookingSaveReqVO updateReqVO) {
        meetingBookingService.updateMeetingBookingByApplicant(getLoginUserId(), updateReqVO);
        return success(true);
    }

    @PutMapping("/cancel-my")
    @Operation(summary = "员工取消本人未开始会议室预定")
    public CommonResult<Boolean> cancelMyMeetingBooking(@Valid @RequestBody MeetingBookingCancelReqVO cancelReqVO) {
        meetingBookingService.cancelMeetingBookingByApplicant(getLoginUserId(), cancelReqVO);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "管理员删除会议室预定")
    @PreAuthorize("@ss.hasPermission('system:meeting-booking:delete')")
    public CommonResult<Boolean> deleteMeetingBooking(@Valid MeetingBookingCancelReqVO cancelReqVO) {
        meetingBookingService.deleteMeetingBookingByAdmin(getLoginUserId(), cancelReqVO);
        return success(true);
    }

    @GetMapping("/get")
    @Operation(summary = "获得会议室预定")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<MeetingBookingRespVO> getMeetingBooking(@RequestParam("id") Long id) {
        MeetingBookingDO booking = meetingBookingService.getMeetingBooking(id);
        validateBookingReadPermission(booking);
        return success(toRespVO(booking));
    }

    @GetMapping("/page")
    @Operation(summary = "管理员获得会议室预定分页")
    @PreAuthorize("@ss.hasPermission('system:meeting-booking:query')")
    public CommonResult<PageResult<MeetingBookingRespVO>> getMeetingBookingPage(@Valid MeetingBookingPageReqVO pageReqVO) {
        return success(toRespPage(meetingBookingService.getMeetingBookingPage(pageReqVO)));
    }

    @GetMapping("/my-page")
    @Operation(summary = "员工获得本人会议室预定分页")
    public CommonResult<PageResult<MeetingBookingRespVO>> getMyMeetingBookingPage(@Valid MeetingBookingPageReqVO pageReqVO) {
        return success(toRespPage(meetingBookingService.getMyMeetingBookingPage(getLoginUserId(), pageReqVO)));
    }

    @PostMapping("/check-conflict")
    @Operation(summary = "检查会议室预定冲突")
    public CommonResult<List<MeetingBookingConflictRespVO>> checkConflict(@Valid @RequestBody MeetingBookingConflictCheckReqVO reqVO) {
        List<MeetingBookingDO> list = meetingBookingService.checkConflictList(reqVO);
        Map<Long, MeetingRoomDO> roomMap = buildMeetingRoomMap(list);
        Map<Long, AdminUserDO> userMap = buildUserMap(list);
        return success(list.stream().map(item -> {
            MeetingBookingConflictRespVO respVO = BeanUtils.toBean(item, MeetingBookingConflictRespVO.class);
            MeetingRoomDO room = roomMap.get(item.getMeetingRoomId());
            if (room != null) {
                respVO.setMeetingRoomName(room.getName());
            }
            AdminUserDO user = userMap.get(item.getApplicantUserId());
            if (user != null) {
                respVO.setApplicantUserNickname(user.getNickname());
            }
            return respVO;
        }).collect(Collectors.toList()));
    }

    @GetMapping("/schedule/week")
    @Operation(summary = "获得周视图排期")
    public CommonResult<List<MeetingBookingRespVO>> getWeekSchedule(@Valid MeetingBookingScheduleReqVO reqVO) {
        return success(toRespList(meetingBookingService.getWeekScheduleList(reqVO)));
    }

    @GetMapping("/schedule/month")
    @Operation(summary = "获得月视图排期")
    public CommonResult<List<MeetingBookingRespVO>> getMonthSchedule(@Valid MeetingBookingScheduleReqVO reqVO) {
        return success(toRespList(meetingBookingService.getMonthScheduleList(reqVO)));
    }

    private PageResult<MeetingBookingRespVO> toRespPage(PageResult<MeetingBookingDO> pageResult) {
        return new PageResult<>(toRespList(pageResult.getList()), pageResult.getTotal());
    }

    private List<MeetingBookingRespVO> toRespList(List<MeetingBookingDO> list) {
        if (CollUtil.isEmpty(list)) {
            return Collections.emptyList();
        }
        Map<Long, MeetingRoomDO> roomMap = buildMeetingRoomMap(list);
        Map<Long, AdminUserDO> userMap = buildUserMap(list);
        return list.stream().map(item -> toRespVO(item, roomMap, userMap)).collect(Collectors.toList());
    }

    private MeetingBookingRespVO toRespVO(MeetingBookingDO booking) {
        if (booking == null) {
            return null;
        }
        return toRespVO(booking, buildMeetingRoomMap(Collections.singletonList(booking)), buildUserMap(Collections.singletonList(booking)));
    }

    private MeetingBookingRespVO toRespVO(MeetingBookingDO booking, Map<Long, MeetingRoomDO> roomMap, Map<Long, AdminUserDO> userMap) {
        MeetingBookingRespVO respVO = BeanUtils.toBean(booking, MeetingBookingRespVO.class);
        MeetingRoomDO room = roomMap.get(booking.getMeetingRoomId());
        if (room != null) {
            respVO.setMeetingRoomName(room.getName());
        }
        AdminUserDO user = userMap.get(booking.getApplicantUserId());
        if (user != null) {
            respVO.setApplicantUserNickname(user.getNickname());
        }
        List<Long> attendeeUserIds = meetingBookingService.getAttendeeUserIds(booking.getId());
        respVO.setAttendeeUserIds(attendeeUserIds);
        respVO.setAttendeeUserNicknames(attendeeUserIds.stream()
                .map(userMap::get)
                .filter(Objects::nonNull)
                .map(AdminUserDO::getNickname)
                .collect(Collectors.toList()));
        return respVO;
    }

    private Map<Long, MeetingRoomDO> buildMeetingRoomMap(List<MeetingBookingDO> list) {
        return list.stream()
                .map(MeetingBookingDO::getMeetingRoomId)
                .filter(Objects::nonNull)
                .distinct()
                .map(meetingRoomService::getMeetingRoom)
                .filter(Objects::nonNull)
                .collect(Collectors.toMap(MeetingRoomDO::getId, item -> item));
    }

    private Map<Long, AdminUserDO> buildUserMap(List<MeetingBookingDO> list) {
        Set<Long> userIds = new LinkedHashSet<>(list.stream()
                .map(MeetingBookingDO::getApplicantUserId)
                .filter(Objects::nonNull)
                .collect(Collectors.toList()));
        list.stream()
                .map(MeetingBookingDO::getId)
                .filter(Objects::nonNull)
                .forEach(bookingId -> userIds.addAll(meetingBookingService.getAttendeeUserIds(bookingId)));
        if (CollUtil.isEmpty(userIds)) {
            return Collections.emptyMap();
        }
        return DataPermissionUtils.executeIgnore(() -> adminUserService.getUserList(new ArrayList<>(userIds)).stream()
                .collect(Collectors.toMap(AdminUserDO::getId, item -> item)));
    }

    private void validateBookingReadPermission(MeetingBookingDO booking) {
        if (booking == null) {
            return;
        }
        Long loginUserId = getLoginUserId();
        if (Objects.equals(loginUserId, booking.getApplicantUserId())) {
            return;
        }
        if (permissionService.hasAnyPermissions(loginUserId, "system:meeting-booking:query")) {
            return;
        }
        throw new org.springframework.security.access.AccessDeniedException("无权查看该会议室预定");
    }

}
