import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, subscribeEvents } from '../api';
import type { Task } from '../types';
import StatusPill from '../components/StatusPill';

const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '执行中' },
  { key: 'wait', label: '等待处理' },
  { key: 'done', label: '已完成' },
];

const BOARD_COLUMNS = [
  { key: 'queued', label: '排队' },
  { key: 'running', label: '执行中' },
  { key: 'wait', label: '等待我处理' },
  { key: 'completed', label: '已完成' },
];

export default function Tasks() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState('all');
  const [view, setView] = useState<'list' | 'board'>('list');
  const [error, setError] = useState('');
  const nav = useNavigate();

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .tasks(filter)
        .then((rows) => alive && setTasks(rows))
        .catch((e) => alive && setError(String(e)));
    load();
    // 全局事件流（SSE）：任务/步骤状态变化即刷新，替代 2s 轮询
    const es = subscribeEvents('/api/events', () => load());
    return () => {
      alive = false;
      es.close();
    };
  }, [filter]);

  const open = (t: Task) => t.run_id && nav(`/run/${t.run_id}`);

  const inColumn = (key: string) => {
    if (key === 'wait') return tasks.filter((t) => ['awaiting_approval', 'awaiting_input'].includes(t.status));
    return tasks.filter((t) => t.status === key);
  };

  return (
    <section className="page active">
      <div className="wrap">
        <header className="page-head">
          <div className="page-head-main">
            <span className="eyebrow">Tasks · 10 states</span>
            <h1>任务</h1>
            <p className="page-sub">任务 → 运行 → 步骤三级结构，状态只由后端状态机改变</p>
          </div>
          <div className="head-actions">
            <button className="btn btn-ghost">
              <svg className="ico">
                <use href="#i-filter" />
              </svg>
              我的任务
            </button>
          </div>
        </header>

        <div className="toolbar">
          <div className="seg">
            <button className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}>
              <svg className="ico">
                <use href="#i-list" />
              </svg>
              列表
            </button>
            <button className={view === 'board' ? 'active' : ''} onClick={() => setView('board')}>
              <svg className="ico">
                <use href="#i-board" />
              </svg>
              看板
            </button>
          </div>
          <div className="chips">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                className={`chip${filter === f.key ? ' active' : ''}`}
                onClick={() => setFilter(f.key)}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {error && <div className="banner bad">{error}</div>}

        {view === 'list' ? (
          <div className="task-list">
            <div className="tl-row tl-head">
              <span>任务</span>
              <span>状态</span>
              <span className="who">参与员工</span>
              <span className="s">步骤</span>
              <span className="s">更新</span>
              <span className="s">运行</span>
            </div>
            {tasks.map((t) => (
              <div className="tl-row" key={t.id} onClick={() => open(t)}>
                <span className="t">
                  {t.title} <span className="mono" style={{ color: 'var(--faint)', fontSize: 11 }}>{t.id}</span>
                </span>
                <span>
                  <StatusPill status={t.status} label={t.status_label} />
                </span>
                <span className="who av-stack">
                  <span className="av av-sm tone-sky">需</span>
                  {t.status === 'running' && <span className="av av-sm tone-moss">数</span>}
                </span>
                <span className="s">{t.steps}</span>
                <span className="s">
                  {new Date(t.updated_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                </span>
                <span className="s mono" style={{ fontSize: 10.5 }}>
                  {t.run_id ?? '—'}
                </span>
              </div>
            ))}
            {!tasks.length && <div className="empty-note" style={{ padding: 24 }}>没有符合条件的任务。</div>}
          </div>
        ) : (
          <div className="board">
            {BOARD_COLUMNS.map((c) => {
              const list = inColumn(c.key);
              return (
                <div className="col" key={c.key}>
                  <div className="col-head">
                    <i className="bar" style={{ background: c.key === 'running' ? 'var(--moss)' : c.key === 'wait' ? 'var(--gold)' : '#CFC6B5' }} />
                    <h3>{c.label}</h3>
                    <span className="cnt">{list.length}</span>
                  </div>
                  {list.map((t) => (
                    <article className="tcard" key={t.id} onClick={() => open(t)}>
                      <div className="tl">
                        <span className="tag tag-sky">{t.workspace}</span>
                        <span className="mono">{t.id}</span>
                      </div>
                      <h4>{t.title}</h4>
                      <div className="prog">
                        <i style={{ width: `${t.progress}%` }} />
                      </div>
                      <div className="tf">
                        <StatusPill status={t.status} label={t.status_label} />
                        <span className="mono">{t.steps} 步</span>
                      </div>
                    </article>
                  ))}
                  {!list.length && <div className="empty-note">空</div>}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
