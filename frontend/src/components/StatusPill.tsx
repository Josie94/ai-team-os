const MAP: Record<string, { cls: string; label: string }> = {
  queued: { cls: 'pill-idle', label: '排队' },
  running: { cls: 'pill-run', label: '执行中' },
  awaiting_approval: { cls: 'pill-wait', label: '等待审批' },
  awaiting_input: { cls: 'pill-sky', label: '等待输入' },
  paused: { cls: 'pill-idle', label: '已暂停' },
  completed: { cls: 'pill-done', label: '已完成' },
  failed: { cls: 'pill-fail', label: '失败' },
  cancelled: { cls: 'pill-idle', label: '已取消' },
  rejected: { cls: 'pill-fail', label: '已驳回' },
  archived: { cls: 'pill-idle', label: '已归档' },
  pending: { cls: 'pill-wait', label: '待审批' },
  approved: { cls: 'pill-run', label: '已通过' },
  revise: { cls: 'pill-sky', label: '待修改' },
  done: { cls: 'pill-done', label: '完成' },
};

export default function StatusPill({ status, label }: { status: string; label?: string }) {
  const m = MAP[status] ?? { cls: 'pill-idle', label: status };
  return (
    <span className={`pill ${m.cls}`}>
      <i />
      {label ?? m.label}
    </span>
  );
}
