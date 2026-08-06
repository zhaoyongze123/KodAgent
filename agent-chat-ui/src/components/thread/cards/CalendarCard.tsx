import { CalendarDays, Clock, MapPin, Users } from "lucide-react";
import type { CalendarEventItem, CalendarPayload } from "@/types/agent-block";
import { displayFieldValue } from "@/lib/card-display";

function parseDate(value?: string): Date | undefined {
  if (!value) return undefined;
  // Backend serializes as "yyyy-MM-dd HH:mm:ss"; make it ISO-ish for Safari.
  const normalized = value.includes("T") ? value : value.replace(" ", "T");
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? undefined : date;
}

function two(n: number) {
  return n < 10 ? `0${n}` : String(n);
}

function dayLabel(date?: Date, raw?: string): string {
  if (!date) return raw ? raw.slice(0, 10) : "";
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

function timeLabel(date?: Date, raw?: string): string {
  if (!date) return raw ? raw.slice(11, 16) : "";
  return `${two(date.getHours())}:${two(date.getMinutes())}`;
}

function timeRange(event: CalendarEventItem): string {
  const start = parseDate(event.startTime);
  const end = parseDate(event.endTime);
  const startStr = timeLabel(start, event.startTime);
  const endStr = timeLabel(end, event.endTime);
  if (startStr && endStr) return `${startStr} - ${endStr}`;
  return startStr || endStr || "";
}

function isMeeting(event: CalendarEventItem) {
  return event.sourceType === "MEETING_BOOKING";
}

export function CalendarCard({ payload }: { payload: CalendarPayload }) {
  const events = payload.events ?? [];

  return (
    <div className="my-2 w-full max-w-xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2 text-base font-semibold text-slate-800">
        <CalendarDays className="size-5 text-slate-600" />
        <span>我的日程</span>
        <span className="ml-auto text-xs font-normal text-slate-500">
          共 {events.length} 项
        </span>
      </div>

      {events.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-400">
          该时间段没有日程安排
        </div>
      ) : (
        <ol className="flex flex-col gap-3">
          {events.map((event, index) => {
            const place = event.meetingRoomName || event.location;
            const attendees = event.attendeeUserNicknames ?? [];
            return (
              <li
                key={`${event.title ?? "event"}-${index}`}
                className="flex gap-3 rounded-lg border border-slate-100 bg-slate-50/60 p-3"
              >
                <div className="flex w-20 shrink-0 flex-col text-xs text-slate-500">
                  <span className="text-slate-400">
                    {dayLabel(parseDate(event.startTime), event.startTime)}
                  </span>
                  <span className="mt-0.5 flex items-center gap-1 font-medium text-slate-700">
                    <Clock className="size-3 shrink-0" />
                    {timeRange(event)}
                  </span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-slate-800">
                      {event.title || "未命名日程"}
                    </span>
                    <span
                      className={
                        "shrink-0 rounded px-1.5 py-0.5 text-[11px] " +
                        (isMeeting(event)
                          ? "bg-blue-50 text-blue-600"
                          : "bg-emerald-50 text-emerald-600")
                      }
                    >
                      {isMeeting(event) ? "会议" : "日程"}
                    </span>
                  </div>
                  {place && (
                    <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                      <MapPin className="size-3 shrink-0" />
                      <span className="truncate">{displayFieldValue(event.meetingRoomName ? "会议室" : "地点", place, { domain: "meeting" })}</span>
                    </div>
                  )}
                  {attendees.length > 0 && (
                    <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                      <Users className="size-3 shrink-0" />
                      <span className="truncate">
                        {attendees.slice(0, 5).join("、")}
                        {attendees.length > 5
                          ? ` 等 ${attendees.length} 人`
                          : ""}
                      </span>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
