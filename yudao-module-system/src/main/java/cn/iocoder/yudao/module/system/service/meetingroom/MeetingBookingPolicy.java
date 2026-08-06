package cn.iocoder.yudao.module.system.service.meetingroom;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.module.system.enums.ErrorCodeConstants;

import java.time.Duration;
import java.time.LocalDateTime;

/**
 * Business policy shared by admin and Agent meeting-booking writes.
 *
 * <p>The data model stores a concrete interval rather than a recurrence, so
 * recurrence is deliberately not inferred from repeated natural-language
 * requests. Duplicate submissions are handled by Agent draft idempotency and
 * overlapping active room bookings remain a conflict.</p>
 */
public final class MeetingBookingPolicy {

    public static final long MINUTES_MIN = 15;
    public static final long MINUTES_MAX = 8 * 60;
    public static final long SLOT_MINUTES = 15;
    public static final boolean CROSS_DAY_SUPPORTED = false;
    public static final boolean RECURRENCE_SUPPORTED = false;

    private MeetingBookingPolicy() {
    }

    public static void validate(LocalDateTime startTime, LocalDateTime endTime) {
        if (startTime == null || endTime == null || !startTime.isBefore(endTime)) {
            throw ServiceExceptionUtil.exception(ErrorCodeConstants.MEETING_BOOKING_TIME_INVALID);
        }
        if (!CROSS_DAY_SUPPORTED && !startTime.toLocalDate().equals(endTime.toLocalDate())) {
            throw ServiceExceptionUtil.exception(ErrorCodeConstants.MEETING_BOOKING_CROSS_DAY_NOT_SUPPORTED);
        }
        long seconds = Duration.between(startTime, endTime).getSeconds();
        long durationMinutes = seconds / 60;
        if (seconds % 60 != 0 || startTime.getMinute() % SLOT_MINUTES != 0
                || endTime.getMinute() % SLOT_MINUTES != 0
                || durationMinutes < MINUTES_MIN || durationMinutes > MINUTES_MAX
                || durationMinutes % SLOT_MINUTES != 0) {
            throw ServiceExceptionUtil.exception(ErrorCodeConstants.MEETING_BOOKING_TIME_SLOT_INVALID);
        }
    }
}
