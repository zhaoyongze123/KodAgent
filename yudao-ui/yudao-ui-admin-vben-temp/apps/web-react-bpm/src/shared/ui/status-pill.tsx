import { cn } from '@/shared/lib/cn';

interface StatusPillProps {
  status?: number;
}

const statusMap: Record<number, { className: string; label: string }> = {
  1: { className: 'running', label: '进行中' },
  2: { className: 'approved', label: '已通过' },
  3: { className: 'rejected', label: '已驳回' },
  4: { className: 'cancelled', label: '已取消' },
};

export function StatusPill({ status }: StatusPillProps) {
  const item = statusMap[status || 1] ?? statusMap[1]!;
  return <span className={cn('status-pill', item.className)}>{item.label}</span>;
}
