import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, subscribeEvents } from '../api';
import type { Approval } from '../types';

const RISK_LABEL: Record<string, string> = { high: '高风险', mid: '中风险', low: '低风险' };

export default function Approvals() {
  const [tab, setTab] = useState<'pending' | 'done'>('pending');
  const [rows, setRows] = useState<Approval[]>([]);
  const [policy, setPolicy] = useState<Record<'high' | 'mid' | 'low', { label: string }[]> | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  const load = () => {
    api
      .approvals(tab === 'pending' ? 'pending' : 'all')
      .then((list) => setRows(tab === 'pending' ? list : list.filter((a) => a.status !== 'pending')))
      .catch((e) => setError(String(e)));
  };

  useEffect(() => {
    load();
    // 全局事件流（SSE）：审批挂起/决策实时刷新，替代 2s 轮询
    const es = subscribeEvents('/api/events', () => load());
    const t = setInterval(load, 30000); // 兜底：等待时长字段随时间增长
    return () => {
      es.close();
      clearInterval(t);
    };
  }, [tab]);

  useEffect(() => {
    api.policy().then(setPolicy).catch(() => undefined);
  }, []);

  async function decide(a: Approval, decision: 'approve' | 'reject' | 'revise') {
    const note =
      decision === 'reject'
        ? window.prompt('驳回原因（写入 audit）', '外发内容缺少评审人确认') ?? ''
        : decision === 'revise'
          ? window.prompt('修改要求（运行会转入等待输入）', '补充 DAG 示意图后再评审') ?? ''
          : undefined;
    setBusy(a.id);
    try {
      await api.decide(a.id, decision, note ?? undefined);
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy('');
    }
  }

  const pendingCount = rows.filter((a) => a.status === 'pending').length;

  return (
    <section className="page active">
      <div className="wrap">
        <header className="page-head">
          <div className="page-head-main">
            <span className="eyebrow">Approvals · Resume at breakpoint</span>
            <h1>审批中心</h1>
            <p className="page-sub">高风险与白名单外的动作在此挂起；决定后从落库的 Run / Step 断点继续</p>
          </div>
          <div className="head-actions">
            <span className="pill pill-wait" style={{ height: 28 }}>
              <i />
              <b>{pendingCount}</b>&nbsp;项待处理
            </span>
          </div>
        </header>

        <div className="tabs">
          <button className={`tab${tab === 'pending' ? ' active' : ''}`} onClick={() => setTab('pending')}>
            待我审批
          </button>
          <button className={`tab${tab === 'done' ? ' active' : ''}`} onClick={() => setTab('done')}>
            已处理
          </button>
        </div>

        {error && <div className="banner bad">{error}</div>}

        <div className="ap-layout">
          <div>
            {rows.map((a) => (
              <article className="approval" key={a.id}>
                <div className="ap-top">
                  <span className={`risk risk-${a.risk}`}>{RISK_LABEL[a.risk]}</span>
                  <span className="tag tag-clay">{a.action}</span>
                  <span className="mono">{a.id}</span>
                  <span className="wait">
                    <svg className="ico" style={{ width: 13, height: 13 }}>
                      <use href="#i-clock" />
                    </svg>
                    {a.status === 'pending' ? `已等待 ${Math.round(a.wait_seconds / 60)} 分钟` : a.status}
                  </span>
                </div>
                <h3>{a.summary}</h3>
                <p className="ap-desc">
                  任务「{a.task_title}」的 step {a.step_seq}，运行{' '}
                  <Link to={`/run/${a.run_id}`} className="mono">
                    {a.run_id}
                  </Link>
                  。
                </p>
                <div className="ap-detail">
                  {Object.entries(a.detail || {}).map(([k, v]) => (
                    <div key={k}>
                      <span className="k">{k}</span>
                      {typeof v === 'string' ? v : JSON.stringify(v)}
                    </div>
                  ))}
                </div>
                <div className="ap-meta">
                  <span>风险等级由工具注册表定义</span>
                  <span>·</span>
                  <span>{a.decided_by ? `处理人 ${a.decided_by}` : '待你处理'}</span>
                  {a.note && <span>· 备注 {a.note}</span>}
                </div>
                {a.status === 'pending' ? (
                  <div className="ap-actions">
                    <button className="btn btn-moss" disabled={busy === a.id} onClick={() => decide(a, 'approve')}>
                      <svg className="ico">
                        <use href="#i-check" />
                      </svg>
                      通过并继续
                    </button>
                    <button className="btn btn-ghost" disabled={busy === a.id} onClick={() => decide(a, 'reject')}>
                      <svg className="ico">
                        <use href="#i-x" />
                      </svg>
                      拒绝
                    </button>
                    <button className="btn btn-ghost" disabled={busy === a.id} onClick={() => decide(a, 'revise')}>
                      请求修改
                    </button>
                    <span className="hint">同一 action 仅挂起一次，重复请求幂等</span>
                  </div>
                ) : (
                  <div className="ap-actions">
                    <span className="tag tag-moss">{a.status}</span>
                    <span className="hint">决定已写入 audit</span>
                  </div>
                )}
              </article>
            ))}
            {!rows.length && <div className="empty-note">队列已清空，没有待处理审批。</div>}
          </div>

          <div className="side-stack">
            <div className="panel">
              <div className="panel-head">
                <h3>审批策略</h3>
                <span className="count">白名单 + 风险等级</span>
              </div>
              <div className="panel-body">
                <div className="policy">
                  <i className="b" style={{ background: 'var(--clay)' }} />
                  <div>
                    <b>高风险：必须人工</b>
                    <span>
                      {(policy?.high ?? []).map((t) => t.label).join('、') || '外发消息、删除文件、写外部系统'}
                    </span>
                  </div>
                </div>
                <div className="policy">
                  <i className="b" style={{ background: 'var(--gold)' }} />
                  <div>
                    <b>中风险：白名单内免审</b>
                    <span>
                      {(policy?.mid ?? []).map((t) => `${t.label}`).join('、') || '项目交付物目录内写入'}
                    </span>
                  </div>
                </div>
                <div className="policy">
                  <i className="b" style={{ background: 'var(--moss)' }} />
                  <div>
                    <b>低风险：直接执行</b>
                    <span>{(policy?.low ?? []).map((t) => t.label).join('、') || '搜索、抓取、读取项目内文件'}</span>
                  </div>
                </div>
                <p className="hint" style={{ marginTop: 8 }}>
                  权限校验在服务端完成，提示词不是安全边界；所有决定写入 audit。
                </p>
              </div>
            </div>

            <div className="panel">
              <div className="panel-head">
                <h3>本项目审批</h3>
              </div>
              <div className="panel-body">
                <div className="dl">
                  <span className="k">待处理</span>
                  <span className="v">{pendingCount} 项</span>
                </div>
                <div className="dl">
                  <span className="k">已处理</span>
                  <span className="v">{tab === 'done' ? rows.length : '—'}</span>
                </div>
                <div className="dl">
                  <span className="k">决策落库</span>
                  <span className="v">audit_events</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
