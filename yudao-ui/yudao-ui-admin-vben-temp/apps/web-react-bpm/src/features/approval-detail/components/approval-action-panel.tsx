import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import {
  approveTask,
  copyTask,
  delegateTask,
  getChildrenTaskList,
  getReturnNodeList,
  rejectTask,
  returnTask,
  signCreateTask,
  signDeleteTask,
  transferTask,
  type Task,
} from '@/entities/task/api/task-api';
import { getSimpleUserList } from '@/entities/user/api/user-api';

interface ApprovalActionPanelProps {
  processInstanceId: string;
  task?: Task;
}

export function ApprovalActionPanel({
  processInstanceId,
  task,
}: ApprovalActionPanelProps) {
  const [approveReason, setApproveReason] = useState('同意');
  const [rejectReason, setRejectReason] = useState('');
  const [reason, setReason] = useState('');
  const [userIdValue, setUserIdValue] = useState('');
  const [returnNode, setReturnNode] = useState('');
  const [copyUserIds, setCopyUserIds] = useState('');
  const [signType, setSignType] = useState<'after' | 'before'>('before');
  const [deleteSignTaskId, setDeleteSignTaskId] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  const userQuery = useQuery({
    queryKey: ['approval-users'],
    queryFn: getSimpleUserList,
  });
  const returnNodesQuery = useQuery({
    enabled: Boolean(task?.id),
    queryKey: ['return-nodes', task?.id],
    queryFn: () => getReturnNodeList(task?.id || ''),
  });
  const childTaskQuery = useQuery({
    enabled: Boolean(task?.id),
    queryKey: ['child-tasks', task?.id],
    queryFn: () => getChildrenTaskList(task?.id || ''),
  });

  function validateTaskReady() {
    return task?.id ? null : '当前没有可处理的待办任务';
  }

  function runWithGuard(
    validate: () => string | null,
    action: () => Promise<unknown>,
  ) {
    return async () => {
      const validationMessage = validate();
      if (validationMessage) {
        setErrorMessage(validationMessage);
        throw new Error(validationMessage);
      }
      setErrorMessage('');
      return action();
    };
  }

  const approveMutation = useMutation({
    mutationFn: runWithGuard(
      () => validateTaskReady(),
      () =>
        approveTask({
          id: task?.id,
          nextAssignees: {},
          reason: approveReason.trim() || '同意',
          variables: {},
        }),
    ),
  });
  const rejectMutation = useMutation({
    mutationFn: runWithGuard(
      () => {
        const baseError = validateTaskReady();
        if (baseError) {
          return baseError;
        }
        return rejectReason.trim() ? null : '驳回必须填写审批意见';
      },
      () =>
        rejectTask({
          id: task?.id,
          reason: rejectReason.trim(),
        }),
    ),
  });
  const delegateMutation = useMutation({
    mutationFn: runWithGuard(
      () => {
        const baseError = validateTaskReady();
        if (baseError) {
          return baseError;
        }
        if (!userIdValue.trim()) {
          return '委派必须指定接收人';
        }
        return reason.trim() ? null : '委派必须填写原因';
      },
      () =>
        delegateTask({
          delegateUserId: Number(userIdValue),
          id: task?.id,
          reason: reason.trim(),
        }),
    ),
  });
  const transferMutation = useMutation({
    mutationFn: runWithGuard(
      () => {
        const baseError = validateTaskReady();
        if (baseError) {
          return baseError;
        }
        if (!userIdValue.trim()) {
          return '转派必须指定新审批人';
        }
        return reason.trim() ? null : '转派必须填写原因';
      },
      () =>
        transferTask({
          assigneeUserId: Number(userIdValue),
          id: task?.id,
          reason: reason.trim(),
        }),
    ),
  });
  const signCreateMutation = useMutation({
    mutationFn: runWithGuard(
      () => {
        const baseError = validateTaskReady();
        if (baseError) {
          return baseError;
        }
        if (!userIdValue.trim()) {
          return '加签必须指定加签人';
        }
        return reason.trim() ? null : '加签必须填写原因';
      },
      () =>
        signCreateTask({
          id: task?.id,
          reason: reason.trim(),
          type: signType,
          userIds: [Number(userIdValue)],
        }),
    ),
  });
  const signDeleteMutation = useMutation({
    mutationFn: runWithGuard(
      () => {
        if (!deleteSignTaskId) {
          return '减签必须选择一个子任务';
        }
        return reason.trim() ? null : '减签必须填写原因';
      },
      () =>
        signDeleteTask({
          id: deleteSignTaskId,
          reason: reason.trim(),
        }),
    ),
  });
  const returnMutation = useMutation({
    mutationFn: runWithGuard(
      () => {
        const baseError = validateTaskReady();
        if (baseError) {
          return baseError;
        }
        if (!returnNode) {
          return '退回必须选择目标节点';
        }
        return reason.trim() ? null : '退回必须填写原因';
      },
      () =>
        returnTask({
          id: task?.id,
          reason: reason.trim(),
          targetTaskDefinitionKey: returnNode,
        }),
    ),
  });
  const copyMutation = useMutation({
    mutationFn: runWithGuard(
      () => {
        const baseError = validateTaskReady();
        if (baseError) {
          return baseError;
        }
        const values = copyUserIds
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean);
        return values.length > 0 ? null : '抄送必须至少填写一个用户编号';
      },
      () =>
        copyTask({
          copyUserIds: copyUserIds
            .split(',')
            .map((item) => Number(item.trim()))
            .filter(Boolean),
          id: task?.id,
          reason: reason.trim(),
        }),
    ),
  });

  const userHints = (userQuery.data || [])
    .slice(0, 4)
    .map((item) => `${item.nickname}:${item.id}`)
    .join(' / ');

  const actionButtons = [
    { action: () => approveMutation.mutate(), label: '通过' },
    { action: () => rejectMutation.mutate(), label: '驳回' },
    { action: () => delegateMutation.mutate(), label: '委派' },
    { action: () => transferMutation.mutate(), label: '转派' },
    { action: () => signCreateMutation.mutate(), label: '加签' },
    { action: () => signDeleteMutation.mutate(), label: '减签' },
    { action: () => returnMutation.mutate(), label: '退回' },
    { action: () => copyMutation.mutate(), label: '抄送' },
  ];
  const mutationPending =
    approveMutation.isPending ||
    rejectMutation.isPending ||
    delegateMutation.isPending ||
    transferMutation.isPending ||
    signCreateMutation.isPending ||
    signDeleteMutation.isPending ||
    returnMutation.isPending ||
    copyMutation.isPending;

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">高级动作</div>
          <h3>审批处理台</h3>
        </div>
        <div className="text-xs text-[var(--text-muted)]">
          {task?.name || '暂无待处理任务'}
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-2">
        <div className="detail-block">
          <div className="work-meta">流程实例</div>
          <div className="mt-2 text-sm font-medium tabular-nums">{processInstanceId}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">待办状态</div>
          <div className="mt-2 text-sm font-medium">
            {task?.id ? '可处理' : '当前无待办'}
          </div>
        </div>
      </div>

      <div className="px-4 py-4">
        <div className="mb-3 grid grid-cols-2 gap-2">
          {actionButtons.map((item) => (
            <button
              key={item.label}
              className="border border-[var(--line)] bg-white px-3 py-2 text-sm"
              disabled={mutationPending || (!task?.id && item.label !== '减签')}
              type="button"
              onClick={item.action}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="space-y-3">
        <div>
          <label className="mb-2 block text-sm font-medium">通过意见</label>
          <input
            className="w-full border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none"
            value={approveReason}
            onChange={(event) => setApproveReason(event.target.value)}
          />
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium">驳回意见</label>
          <textarea
            className="w-full border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none"
            rows={2}
            value={rejectReason}
            onChange={(event) => setRejectReason(event.target.value)}
          />
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium">通用原因</label>
          <textarea
            className="w-full border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none"
            placeholder="委派、转派、加签、减签、退回、抄送时填写"
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium">用户编号</label>
          <input
            className="w-full border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none"
            placeholder={`委派/转派/加签使用。示例：${userHints}`}
            value={userIdValue}
            onChange={(event) => setUserIdValue(event.target.value)}
          />
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium">加签类型</label>
          <select
            className="w-full border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none"
            value={signType}
            onChange={(event) => setSignType(event.target.value as 'after' | 'before')}
          >
            <option value="before">前加签</option>
            <option value="after">后加签</option>
          </select>
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium">退回节点</label>
          <select
            className="w-full border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none"
            value={returnNode}
            onChange={(event) => setReturnNode(event.target.value)}
          >
            <option value="">请选择节点</option>
            {(returnNodesQuery.data || []).map((item) => (
              <option key={String(item.taskDefinitionKey)} value={String(item.taskDefinitionKey)}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium">减签目标</label>
          <select
            className="w-full border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none"
            value={deleteSignTaskId}
            onChange={(event) => setDeleteSignTaskId(event.target.value)}
          >
            <option value="">请选择子任务</option>
            {(childTaskQuery.data || []).map((item) => (
              <option key={item.id} value={item.id}>
                {(item.assigneeUser?.nickname || item.ownerUser?.nickname || '未指派') +
                  ' · ' +
                  item.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium">抄送用户编号</label>
          <input
            className="w-full border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none"
            placeholder="多个编号逗号分隔"
            value={copyUserIds}
            onChange={(event) => setCopyUserIds(event.target.value)}
          />
        </div>
        {errorMessage ? (
          <div className="border border-[#dfb2aa] bg-[#fff6f4] px-3 py-2 text-sm text-[var(--danger)]">
            {errorMessage}
          </div>
        ) : null}
        </div>
      </div>
    </section>
  );
}
