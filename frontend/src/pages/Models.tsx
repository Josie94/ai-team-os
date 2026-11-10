import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Provider, Tool } from '../types';

const RISK: Record<string, { label: string; cls: string }> = {
  high: { label: '高风险', cls: 'tag-clay' },
  mid: { label: '中风险', cls: 'tag-gold' },
  low: { label: '低风险', cls: 'tag-moss' },
};

export default function Models() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [msg, setMsg] = useState('');
  const [form, setForm] = useState({ name: '', provider: 'openai-compatible', model: '', base_url: '', api_key: '' });

  const load = () =>
    api
      .models()
      .then((d) => {
        setProviders(d.providers);
        setTools(d.tools);
      })
      .catch((e) => setMsg(String(e)));

  useEffect(() => {
    load();
  }, []);

  async function add() {
    if (!form.name || !form.model || !form.base_url) {
      setMsg('name / model / base_url 必填');
      return;
    }
    try {
      await api.createModel({ ...form });
      setForm({ name: '', provider: 'openai-compatible', model: '', base_url: '', api_key: '' });
      setMsg('已添加，执行引擎无需改动');
      load();
    } catch (e) {
      setMsg(String(e));
    }
  }

  return (
    <section className="page active">
      <div className="wrap">
        <header className="page-head">
          <div className="page-head-main">
            <span className="eyebrow">Model Gateway · OpenAI 兼容</span>
            <h1>模型</h1>
            <p className="page-sub">适配层按 OpenAI 兼容协议实现，新增供应商只需填 base_url / model / key 引用，不改执行引擎</p>
          </div>
        </header>

        {msg && <div className="banner ok">{msg}</div>}

        <div className="model-layout">
          <div className="panel">
            <div className="panel-head">
              <h3>模型档案</h3>
              <span className="count">{providers.length} 个 · key 服务端加密存储</span>
            </div>
            <div className="panel-body">
              {providers.map((p) => (
                <div className="model-row" key={p.id}>
                  <div className="model-ic">{(p.provider || 'AI').slice(0, 2).toUpperCase()}</div>
                  <div className="model-body">
                    <div className="model-name">
                      {p.name}
                      {p.is_default && <span className="tag tag-moss">默认</span>}
                      {p.provider === 'ollama' ? <span className="tag">本地</span> : <span className="tag">OpenAI 兼容</span>}
                    </div>
                    <div className="model-sub mono">
                      {p.model} · base_url {p.base_url} · {p.key_hint}
                    </div>
                    <div className="model-nums">
                      <span>超时 60s</span>
                      <span>流式 支持</span>
                      <span>{p.has_key ? '已配置 key' : '未配置 key（降级模拟）'}</span>
                    </div>
                  </div>
                  <div className="model-act">
                    {!p.is_default && (
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={async () => {
                          await api.setDefaultModel(p.id);
                          setMsg(`默认模型已切换为 ${p.name}`);
                          load();
                        }}
                      >
                        设为默认
                      </button>
                    )}
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={async () => {
                        const r = await api.testModel(p.id);
                        setMsg(`${p.name}：${r.ok ? '可用' : '不可用'} · ${r.reply}`);
                      }}
                    >
                      测试
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y">
            <div className="panel">
              <div className="panel-head">
                <h3>新增供应商</h3>
                <span className="count">不改代码</span>
              </div>
              <div className="panel-body">
                <label className="form-field">
                  名称
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="例如 DeepSeek V3" />
                </label>
                <label className="form-field">
                  model
                  <input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} placeholder="deepseek-chat" />
                </label>
                <label className="form-field">
                  base_url
                  <input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://api.deepseek.com" />
                </label>
                <label className="form-field">
                  api key（可留空，留空走降级模拟）
                  <input
                    type="password"
                    value={form.api_key}
                    onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                    placeholder="sk-..."
                  />
                </label>
                <button className="btn btn-primary" style={{ width: '100%' }} onClick={add}>
                  <svg className="ico">
                    <use href="#i-plus" />
                  </svg>
                  添加
                </button>
              </div>
            </div>

            <div className="panel">
              <div className="panel-head">
                <h3>工具风险注册表</h3>
                <span className="count">{tools.length} 个</span>
              </div>
              <div className="panel-body">
                {tools.map((t) => (
                  <div className="tool-row" key={t.name}>
                    <span className={`tag ${RISK[t.risk]?.cls ?? ''}`}>{RISK[t.risk]?.label ?? t.risk}</span>
                    <span className="mono">{t.name}</span>
                    <span className="wl">{t.whitelist?.length ? t.whitelist.join(', ') : '无白名单'}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
