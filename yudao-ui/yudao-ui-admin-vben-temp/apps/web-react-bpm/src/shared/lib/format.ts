import dayjs from 'dayjs';

export function formatDateTime(value?: number | string | Date | null) {
  if (!value) {
    return '-';
  }
  return dayjs(value).format('YYYY-MM-DD HH:mm');
}

export function formatDuration(durationInMillis?: number | null) {
  if (!durationInMillis || durationInMillis <= 0) {
    return '-';
  }
  const minutes = Math.floor(durationInMillis / 1000 / 60);
  if (minutes < 60) {
    return `${minutes} 分钟`;
  }
  const hours = Math.floor(minutes / 60);
  const remainMinutes = minutes % 60;
  return `${hours} 小时 ${remainMinutes} 分钟`;
}
