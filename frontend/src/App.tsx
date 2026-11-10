import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import Sprite from './components/Sprite';
import { api, subscribeEvents } from './api';
import Chat from './pages/Chat';
import Tasks from './pages/Tasks';
import Run from './pages/Run';
import Approvals from './pages/Approvals';
import Models from './pages/Models';
import Placeholder from './pages/Placeholder';

const NAV = [
  { to: '/', key: 'chat', icon: 'i-chat', label: '对话' },
  { to: '/tasks', key: 'tasks', icon: 'i-tasks', label: '任务' },
  { to: '/models', key: 'models', icon: 'i-cpu', label: '模型' },
  { to: '/approvals', key: 'approvals', icon: 'i-shield', label: '审批' },
  { to: '/employees', key: 'employees', icon: 'i-people', label: '员工' },
  { to: '/kb', key: 'kb', icon: 'i-book', label: '知识库' },
];

export default function App() {
  const [pending, setPending] = useState(0);

  useEffect(() => {
    let alive = true;
    const tick = () =>
      api
        .stats()
        .then((s) => alive && setPending(s.pending_approvals))
        .catch(() => undefined);
    tick();
    // 全局事件流（SSE）：审批挂起/决策实时更新徽章，替代 3s 轮询
    const es = subscribeEvents('/api/events', () => tick());
    return () => {
      alive = false;
      es.close();
    };
  }, []);

  return (
    <>
      <Sprite />
      <div className="shell">
        <nav className="navrail">
          <div className="nav-brand">
            <svg className="ico">
              <use href="#i-spark" />
            </svg>
          </div>
          <div className="nav-items">
            {NAV.map((n) => (
              <NavLink
                key={n.key}
                to={n.to}
                end={n.to === '/'}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
                title={n.label}
              >
                <svg className="ico">
                  <use href={`#${n.icon}`} />
                </svg>
                {n.label}
                {n.key === 'approvals' && pending > 0 && <span className="nav-badge">{pending}</span>}
              </NavLink>
            ))}
          </div>
          <div className="nav-foot">
            <button className="nav-av" title="账号与设置">
              我
            </button>
          </div>
        </nav>

        <div className="stage">
          <Routes>
            <Route path="/" element={<Chat />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/run/:id" element={<Run />} />
            <Route path="/approvals" element={<Approvals />} />
            <Route path="/models" element={<Models />} />
            <Route
              path="/employees"
              element={
                <Placeholder
                  eyebrow="Agents · Phase 1 单智能体"
                  title="员工"
                  sub="Phase 1 只有 1 位默认智能体；多角色组队在 Phase 2 的 DAG 调度中开启。"
                />
              }
            />
            <Route
              path="/kb"
              element={
                <Placeholder
                  eyebrow="Knowledge · Phase 3"
                  title="业务知识库"
                  sub="指标定义、业务规则与背景知识，Phase 3 接入 pgvector 后开启召回与引用追溯。"
                />
              }
            />
            <Route
              path="/skills"
              element={
                <Placeholder eyebrow="Skills · Phase 2" title="技能" sub="提示词模板 + 工具编排的复用单元，Phase 2 上线。" />
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </div>
    </>
  );
}
