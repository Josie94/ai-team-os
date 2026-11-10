import type {
  Approval,
  Conversation,
  Message,
  Provider,
  RunDetail,
  Task,
  Tool,
} from './types';

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  stats: () => req<{ pending_approvals: number; tasks: number; running: number; completed: number }>('/api/stats'),

  conversations: () => req<Conversation[]>('/api/conversations'),
  messages: (cid: string) => req<Message[]>(`/api/conversations/${cid}/messages`),
  chat: (text: string, conversation_id?: string) =>
    req<{ conversation_id: string; reply: string; task_id: string | null; run_id: string | null }>(
      '/api/chat',
      { method: 'POST', body: JSON.stringify({ text, conversation_id }) },
    ),
  chatStream: (
    text: string,
    conversation_id: string | null | undefined,
    onMeta: (m: { conversation_id: string; task_id: string | null; run_id: string | null }) => void,
    onDelta: (t: string) => void,
  ) =>
    new Promise<{ conversation_id: string; task_id: string | null; run_id: string | null; message_id: number }>(
      async (resolve, reject) => {
        try {
          const res = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, conversation_id: conversation_id ?? undefined }),
          });
          if (!res.ok || !res.body) throw new Error(await res.text());
          const reader = res.body.getReader();
          const dec = new TextDecoder();
          let buf = '';
          const meta: { conversation_id: string; task_id: string | null; run_id: string | null } = {
            conversation_id: '',
            task_id: null,
            run_id: null,
          };
          let done: { conversation_id: string; task_id: string | null; run_id: string | null; message_id: number } | null = null;
          for (;;) {
            const { value, done: ended } = await reader.read();
            if (ended) break;
            buf += dec.decode(value, { stream: true });
            let idx: number;
            while ((idx = buf.indexOf('\n\n')) >= 0) {
              const frame = buf.slice(0, idx);
              buf = buf.slice(idx + 2);
              let ev = 'message';
              let data = '';
              for (const line of frame.split('\n')) {
                if (line.startsWith('event:')) ev = line.slice(6).trim();
                else if (line.startsWith('data:')) data += line.slice(5).trim();
              }
              if (!data) continue;
              let obj: Record<string, unknown>;
              try {
                obj = JSON.parse(data);
              } catch {
                continue;
              }
              if (ev === 'meta') {
                Object.assign(meta, obj);
                onMeta({ ...meta });
              } else if (ev === 'delta') {
                onDelta(String(obj.text ?? ''));
              } else if (ev === 'done') {
                done = {
                  conversation_id: String(obj.conversation_id ?? meta.conversation_id),
                  task_id: (obj.task_id as string | null) ?? meta.task_id,
                  run_id: (obj.run_id as string | null) ?? meta.run_id,
                  message_id: Number(obj.message_id ?? 0),
                };
              }
            }
          }
          resolve(done ?? { ...meta, message_id: 0 });
        } catch (e) {
          reject(e);
        }
      },
    ),

  tasks: (status = 'all') => req<Task[]>(`/api/tasks?status=${status}`),
  run: (rid: string) => req<RunDetail>(`/api/runs/${rid}`),
  pauseRun: (rid: string) => req(`/api/runs/${rid}/pause`, { method: 'POST' }),
  cancelRun: (rid: string) => req(`/api/runs/${rid}/cancel`, { method: 'POST' }),
  submitInput: (rid: string, text: string) =>
    req(`/api/runs/${rid}/input`, { method: 'POST', body: JSON.stringify({ text }) }),

  approvals: (status = 'pending') => req<Approval[]>(`/api/approvals?status=${status}`),
  decide: (aid: string, decision: 'approve' | 'reject' | 'revise', note?: string) =>
    req<{ ok: boolean; status: string }>(`/api/approvals/${aid}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, note }),
    }),
  policy: () => req<Record<'high' | 'mid' | 'low', { name: string; label: string; whitelist: string[] }[]>>('/api/policy'),

  models: () => req<{ providers: Provider[]; tools: Tool[] }>('/api/models'),
  createModel: (payload: {
    name: string;
    provider: string;
    model: string;
    base_url: string;
    api_key?: string;
    is_default?: boolean;
  }) => req<Provider>('/api/models', { method: 'POST', body: JSON.stringify(payload) }),
  setDefaultModel: (id: string) => req<Provider>(`/api/models/${id}/default`, { method: 'POST' }),
  testModel: (id: string) =>
    req<{ ok: boolean; live: boolean; reply: string; error: string | null }>(`/api/models/${id}/test`, {
      method: 'POST',
    }),
};

/** 订阅 SSE 事件流（全局 /api/events 或单运行 /api/runs/:id/stream）。
 *  事件即刷新信号：收到后按需重拉数据，SSE 不承载数据本身。
 *  返回 EventSource，调用方在卸载时 close()；断线由浏览器自动重连。 */
const EVENT_NAMES = [
  'task.created',
  'run.started',
  'run.completed',
  'run.failed',
  'run.cancelled',
  'step.started',
  'step.completed',
  'approval.requested',
  'approval.approved',
  'approval.rejected',
  'approval.revise_requested',
  'run.input_provided',
] as const;

export function subscribeEvents(path: string, onEvent: (event: string) => void): EventSource {
  const es = new EventSource(path);
  EVENT_NAMES.forEach((name) => {
    es.addEventListener(name, () => onEvent(name));
  });
  es.onerror = () => undefined; // EventSource 自带重连，静默即可
  return es;
}
