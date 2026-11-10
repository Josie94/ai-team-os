import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import type { Conversation, Message } from '../types';

const TONES = ['tone-gold', 'tone-sky', 'tone-clay', 'tone-moss', 'tone-ink'];

export default function Chat() {
  const [convos, setConvos] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [lastRun, setLastRun] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .conversations()
      .then((rows) => {
        setConvos(rows);
        if (rows.length) setCurrent(rows[0].id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!current) return;
    api.messages(current).then(setMessages).catch((e) => setError(String(e)));
  }, [current]);

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const grouped = useMemo(() => {
    const map: Record<string, Conversation[]> = {};
    convos.forEach((c) => {
      (map[c.workspace] ||= []).push(c);
    });
    return map;
  }, [convos]);

  const convo = convos.find((c) => c.id === current);

  async function send(text: string) {
    const content = text.trim();
    if (!content || sending) return;
    setSending(true);
    setError('');
    setInput('');
    const optimistic: Message = {
      id: Date.now(),
      role: 'user',
      agent: '',
      content,
      run_id: null,
      attachment: null,
      created_at: new Date().toISOString(),
    };
    const streamId = -Date.now();
    const streamMsg: Message = {
      id: streamId,
      role: 'assistant',
      agent: 'AI 助手',
      content: '',
      run_id: null,
      attachment: null,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, optimistic, streamMsg]);
    try {
      await api.chatStream(
        content,
        current ?? undefined,
        (meta) => {
          if (meta.conversation_id) setCurrent(meta.conversation_id);
          if (meta.run_id) setLastRun(meta.run_id);
          setMessages((ms) =>
            ms.map((x) =>
              x.id === streamId
                ? {
                    ...x,
                    run_id: meta.run_id ?? x.run_id,
                    agent: meta.run_id ? '需求分析师 · 已组队' : x.agent,
                  }
                : x,
            ),
          );
        },
        (t) => setMessages((ms) => ms.map((x) => (x.id === streamId ? { ...x, content: x.content + t } : x))),
      );
      const list = await api.conversations();
      setConvos(list);
    } catch (e) {
      setError(String(e));
      setMessages((ms) => ms.filter((x) => x.id !== streamId));
    } finally {
      setSending(false);
    }
  }

  async function toTask() {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    if (!lastUser) {
      setError('先在对话里说一句要做什么，再转为任务');
      return;
    }
    try {
      const res = await api.chat(lastUser.content, current ?? undefined);
      if (res.run_id) setLastRun(res.run_id);
      if (res.conversation_id) {
        setCurrent(res.conversation_id);
        setMessages(await api.messages(res.conversation_id));
      }
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <section className="page active" style={{ overflow: 'hidden' }}>
      <div className="chat-shell">
        <aside className="chat-side">
          <div className="cs-top">
            <div>
              <span className="eyebrow">Chat</span>
              <h2>对话</h2>
            </div>
            <button
              className="icon-btn"
              title="新建对话"
              onClick={() => {
                setCurrent(null);
                setMessages([]);
              }}
            >
              <svg className="ico">
                <use href="#i-plus" />
              </svg>
            </button>
          </div>
          <div className="search">
            <svg className="ico">
              <use href="#i-search" />
            </svg>
            <input placeholder="搜索对话、员工或项目" />
          </div>
          <div className="cs-note">
            <svg className="ico">
              <use href="#i-spark2" />
            </svg>
            简单问题直接回答 · 涉及产出自动转任务
          </div>

          <div className="convo-scroll">
            {Object.entries(grouped).map(([ws, list]) => (
              <div key={ws}>
                <div className="group-label">
                  {ws} <span className="ws-meta">{list.length} 条</span>
                </div>
                {list.map((c, i) => (
                  <button
                    key={c.id}
                    className={`convo${c.id === current ? ' active' : ''}`}
                    onClick={() => setCurrent(c.id)}
                  >
                    <span className={`av av-lg ${TONES[i % TONES.length]}`}>{c.title.slice(0, 1)}</span>
                    <div className="convo-body">
                      <div className="convo-line">
                        <span className="convo-name">{c.title}</span>
                        <span className="convo-time">
                          {new Date(c.updated_at).toLocaleTimeString('zh-CN', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>
                      <div className="convo-prev">{c.preview || '还没有消息'}</div>
                    </div>
                    {c.unread > 0 && <span className="unread">{c.unread}</span>}
                  </button>
                ))}
              </div>
            ))}
            {!convos.length && <div className="empty-note" style={{ padding: '12px 18px' }}>还没有会话，直接发消息即可新建。</div>}
          </div>
        </aside>

        <div className="chat-resizer" title="拖动调整会话列表宽度" />

        <div className="chat-main">
          <div className="chat-head">
            <div className="av av-lg tone-gold">{(convo?.title ?? '新').slice(0, 1)}</div>
            <div className="chat-title">
              <h1>{convo?.title ?? '新对话'}</h1>
              <div className="chat-sub">
                <span className="ws-badge">{convo?.workspace ?? '默认工作区'}</span>
                <i />
                <span>{convo?.subtitle || '单智能体执行 · Phase 1'}</span>
              </div>
            </div>
            <div className="chat-actions">
              <button className="btn btn-primary btn-sm" onClick={toTask}>
                <svg className="ico">
                  <use href="#i-tasks" />
                </svg>
                转为任务
              </button>
              {lastRun && (
                <Link className="btn btn-ghost btn-sm" to={`/run/${lastRun}`}>
                  查看运行
                </Link>
              )}
            </div>
          </div>

          <div className="thread-scroll" ref={threadRef}>
            {!messages.length && (
              <div className="chat-welcome">
                <div className="cw-badge">
                  <svg className="ico">
                    <use href="#i-spark" />
                  </svg>
                </div>
                <h2>今天想推进什么？</h2>
                <p>随便问，简单问题直接回答；涉及产出会自动转成任务，跑完在审批中心卡住外发动作。</p>
                <div className="cw-chips">
                  {['整理本周团队周报，按组别汇总进展', '扫描本周竞品动态并去重入库', '撰写白皮书初稿'].map((p) => (
                    <button key={p} onClick={() => send(p)}>
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m) => (
              <div key={m.id} className={`msg${m.role === 'user' ? ' me' : ''}`}>
                <span className={`av av-lg ${m.role === 'user' ? 'tone-ink' : 'tone-sky'}`}>
                  {m.role === 'user' ? '我' : (m.agent || 'AI').slice(0, 1)}
                </span>
                <div>
                  <div className="who">{m.role === 'user' ? '我' : m.agent || 'AI 助手'}</div>
                  <div className={`bubble${m.id < 0 && m.content ? ' streaming' : ''}`}>
                    {m.content || (
                      <span className="typing">
                        <i />
                        <i />
                        <i />
                      </span>
                    )}
                  </div>
                  {m.attachment?.filename && (
                    <div className="share">
                      <b>
                        <svg className="ico" style={{ width: 14, height: 14 }}>
                          <use href="#i-file" />
                        </svg>
                        {m.attachment.filename}
                      </b>
                      <span>
                        {m.attachment.size} {m.attachment.note ? `· ${m.attachment.note}` : ''}
                      </span>
                    </div>
                  )}
                  {m.run_id && (
                    <div className="msg-note">
                      已创建运行 <Link to={`/run/${m.run_id}`}>{m.run_id}</Link>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {sending && !messages.some((m) => m.id < 0) && (
              <div className="msg">
                <span className="av av-lg tone-clay">需</span>
                <div>
                  <div className="who">需求分析师 · 正在处理</div>
                  <div className="typing">
                    <i />
                    <i />
                    <i />
                  </div>
                </div>
              </div>
            )}
          </div>

          {error && <div className="empty-note" style={{ padding: '0 24px 6px', color: '#A12A2A' }}>{error}</div>}

          <div className="composer">
            <div className="comp-chips">
              {['生成本周周报', '查本周行业情报', '新建一个项目'].map((s) => (
                <button key={s} className="chip" onClick={() => setInput(s)}>
                  {s}
                </button>
              ))}
            </div>
            <div className="comp-box">
              <textarea
                rows={2}
                value={input}
                placeholder="发消息给 AI 团队，Enter 发送"
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    send(input);
                  }
                }}
              />
              <div className="comp-row">
                <button className="comp-tool" title="上传附件">
                  <svg className="ico">
                    <use href="#i-paper" />
                  </svg>
                </button>
                <span className="hint">回复会带上员工与运行记录</span>
                <button className="btn btn-primary" disabled={sending} onClick={() => send(input)}>
                  <svg className="ico">
                    <use href="#i-send" />
                  </svg>
                  发送
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
