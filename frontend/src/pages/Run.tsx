import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, subscribeEvents } from '../api';
import type { RunDetail } from '../types';
import StatusPill from '../components/StatusPill';
import DagView from '../components/DagView';

function fmtDuration(start?: string | null, end?: string | null) {
  if (!start) return '—';
  const s = new Date(start).getTime();
  const e = end ? new Date(end).getTime() : Date.now();
  const sec = Math.max(0, Math.round((e - s) / 1000));
  return sec < 60 ? `${sec} 秒` : `${Math.floor(sec / 60)} 分 ${sec % 60} 秒`;
}

const EVENT_TONE: Record<string, string> = {
  'run.started': 'moss',
  'step.completed': 'moss',
  'approval.requested': 'gold',
  'approval.approved': 'clay',
  'approval.rejected': 'clay',
  'run.failed': 'clay',
};

export default function Run() {
  const { id = '' } = useParams();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState('');
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setRun(await api.run(id));
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    load();
    // 运行事件流（SSE）：run/step 状态变化即被动刷新，替代轮询；断线由 EventSource 自动重连
    const es = subscribeEvents(`/api/runs/${id}/stream`, () => load());
    const t = setInterval(load, 15000); // 兜底刷新：耗时字段随时间增长
    return () => {
      es.close();
      clearInterval(t);
    };
  }, [id]);

  if (!run) {
    return (
      <section className="page active">
        <div className="page-loading">{error || '加载运行…'}</div>
      </section>
    );
  }

  const pct = run.total_steps ? Math.round((run.done_steps / run.total_steps) * 100) : 0;

  return (
    <section className="page active">
      <div className="wrap">
        <div className="run-top">
          <Link className="crumb" to="/tasks">
            <svg className="ico">
              <use href="#i-back" />
            </svg>
            返回任务
          </Link>
          <span className="mono">
            {run.id} · {run.task_id}
          </span>
          <span className="tag tag-gold">{run.task?.workspace}</span>
          <div className="run-actions">
            <button
              className="btn btn-ghost btn-sm"
              disabled={busy || run.status !== 'running'}
              onClick={async () => {
                setBusy(true);
                await api.pauseRun(run.id).catch((e) => setError(String(e)));
                await load();
                setBusy(false);
              }}
            >
              <svg className="ico">
                <use href="#i-pause" />
              </svg>
              暂停
            </button>
            <button
              className="btn btn-ghost btn-sm"
              disabled={busy || ['completed', 'cancelled', 'rejected'].includes(run.status)}
              onClick={async () => {
                setBusy(true);
                await api.cancelRun(run.id).catch((e) => setError(String(e)));
                await load();
                setBusy(false);
              }}
            >
              <svg className="ico">
                <use href="#i-x" />
              </svg>
              取消
            </button>
          </div>
        </div>

        <div className="run-title-row">
          <div style={{ minWidth: 0 }}>
            <h1>{run.task?.title}</h1>
            <p className="page-sub">{run.task?.goal}</p>
          </div>
        </div>

        <div className="run-stats" style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0,1fr))', gap: 1, background: 'var(--line-soft)', border: '1px solid var(--line-soft)', borderRadius: 13, overflow: 'hidden', margin: '18px 0' }}>
          <div className="stat-cell">
            <div className="k">运行状态</div>
            <div className="v">
              <StatusPill status={run.status} label={run.status_label} />
            </div>
          </div>
          <div className="stat-cell">
            <div className="k">工具调用</div>
            <div className="v">
              <em>{run.tool_calls}</em> 次
            </div>
          </div>
          <div className="stat-cell">
            <div className="k">步骤</div>
            <div className="v">
              <em>{run.done_steps}</em> / {run.total_steps} 步
            </div>
          </div>
          <div className="stat-cell">
            <div className="k">耗时</div>
            <div className="v">{fmtDuration(run.started_at, run.finished_at)}</div>
          </div>
          <div className="stat-cell">
            <div className="k">并发占用</div>
            <div className="v">
              <em>{run.slots_used}</em> / {run.slots_total} 槽
            </div>
          </div>
        </div>

        {run.pending_approval && (
          <div className="banner warn">
            <svg className="ico" style={{ width: 15, height: 15 }}>
              <use href="#i-shield" />
            </svg>
            步骤 {run.pending_approval.step_seq} 命中{run.pending_approval.risk === 'high' ? '高风险' : '中风险'}策略
            <b>{run.pending_approval.action}</b>，已挂起等待审批。
            <Link to="/approvals" style={{ marginLeft: 'auto', color: 'inherit', fontWeight: 700 }}>
              去审批 →
            </Link>
          </div>
        )}
        {run.status === 'awaiting_input' && (
          <div className="banner warn" style={{ display: 'block' }}>
            <div style={{ marginBottom: 8 }}>审批要求修改，补充说明后从当前步骤继续：</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                style={{ flex: 1, height: 34, borderRadius: 8, border: '1px solid var(--line)', padding: '0 10px' }}
                value={input}
                placeholder="例如：把「团队协作」章节的 DAG 图补进去"
                onChange={(e) => setInput(e.target.value)}
              />
              <button
                className="btn btn-primary btn-sm"
                onClick={async () => {
                  await api.submitInput(run.id, input).catch((e) => setError(String(e)));
                  setInput('');
                  load();
                }}
              >
                提交并继续
              </button>
            </div>
          </div>
        )}
        {run.status === 'completed' && <div className="banner ok">运行已完成，交付物与证据链已归档（{pct}%）。</div>}
        {run.status === 'failed' && <div className="banner bad">运行失败：{run.error}</div>}
        {run.status === 'rejected' && <div className="banner bad">审批驳回，运行已终止。</div>}
        {error && <div className="banner bad">{error}</div>}

        <div className="run-grid">
          <div className="panel">
            <div className="panel-head">
              <h3>DAG 执行图</h3>
              <span className="count">{run.dag?.parallel_width ?? 1} 并行</span>
            </div>
            <div className="panel-body">
              <DagView dag={run.dag} steps={run.steps} />
            </div>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h3>步骤</h3>
              <span className="count">
                {run.done_steps} / {run.total_steps}
              </span>
            </div>
            <div className="panel-body" style={{ padding: 0 }}>
              <table className="steps">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>员工</th>
                    <th>步骤</th>
                    <th>工具</th>
                    <th>产出</th>
                    <th>状态</th>
                    <th>耗时</th>
                  </tr>
                </thead>
                <tbody>
                  {run.steps.map((s) => (
                    <tr key={s.id}>
                      <td className="mono">s{s.seq}</td>
                      <td>
                        <b>{s.agent}</b>
                      </td>
                      <td>{s.title}</td>
                      <td className="mono" style={{ fontSize: 11 }}>
                        {s.tool}
                      </td>
                      <td style={{ maxWidth: 240 }}>{s.output ?? '—'}</td>
                      <td>
                        <StatusPill status={s.status} label={s.status_label} />
                      </td>
                      <td className="mono">{s.duration_ms ? `${(s.duration_ms / 1000).toFixed(1)}s` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="space-y">
            <div className="panel">
              <div className="panel-head">
                <h3>事件流</h3>
                <span className="count">audit · {run.events.length} 条</span>
              </div>
              <div className="panel-body">
                {run.events.map((e) => (
                  <div className={`ev ${EVENT_TONE[e.type] ?? ''}`} key={e.seq}>
                    <div className="ev-top">
                      <span className="t">
                        {new Date(e.at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                      <span className="ev-type">{e.type}</span>
                      <span className="mono">#{e.seq}</span>
                    </div>
                    <div className="ev-text">
                      {Object.entries(e.payload)
                        .slice(0, 3)
                        .map(([k, v]) => (
                          <span key={k}>
                            {k}: {String(v).slice(0, 48)}{' '}
                          </span>
                        ))}
                    </div>
                  </div>
                ))}
                {!run.events.length && <div className="empty-note">还没有事件。</div>}
              </div>
            </div>

            <div className="panel deliverable-panel">
              <div className="panel-head">
                <h3>交付物</h3>
                <span className="count">{run.deliverables.length} 个</span>
              </div>
              <div className="panel-body">
                {run.deliverables.map((d) => (
                  <div className="run-row" key={d.filename}>
                    <span className="av av-sm tone-gold">件</span>
                    <div className="run-main">
                      <div className="run-title">{d.filename}</div>
                      <div className="run-meta">
                        <span>{Math.max(1, Math.round(d.size / 1024))} KB</span>
                        <span className="mono">sha256 {d.sha256.slice(0, 8)}…{d.sha256.slice(-4)}</span>
                      </div>
                      <div className="run-meta mono" style={{ fontSize: 10.5 }}>{d.path}</div>
                    </div>
                  </div>
                ))}
                {!run.deliverables.length && <div className="empty-note">初稿生成后会出现在这里。</div>}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
