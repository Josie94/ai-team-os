import type { DagInfo, Step } from '../types';

const TONE: Record<string, string> = {
  done: 'var(--moss-600, #4a7c59)',
  running: 'var(--gold-600, #b8860b)',
  awaiting_approval: 'var(--clay-600, #b4562f)',
  failed: 'var(--clay-600, #b4562f)',
};

/**
 * DAG 图视图：按拓扑层级展示节点与依赖边。
 * 同一层的节点可并行执行（parallel_width 即最大并行宽度）。
 */
export default function DagView({ dag, steps }: { dag: DagInfo | null; steps: Step[] }) {
  if (!dag || !dag.nodes.length) return null;

  const statusBySeq = new Map<number, string>();
  steps.forEach((s) => statusBySeq.set(s.seq, s.status));

  // 计算每个节点的层级（拓扑深度）
  const depth: Record<string, number> = {};
  for (const key of dag.topo_order) {
    const node = dag.nodes.find((n) => n.key === key);
    const parents = node?.depends_on ?? [];
    depth[key] = parents.length ? Math.max(...parents.map((p) => (depth[p] ?? 0) + 1)) : 0;
  }
  const maxDepth = Math.max(0, ...Object.values(depth));

  // 按层分组
  const layers: string[][] = Array.from({ length: maxDepth + 1 }, () => []);
  dag.topo_order.forEach((key) => {
    const d = depth[key] ?? 0;
    layers[d].push(key);
  });

  const byKey = new Map(dag.nodes.map((n) => [n.key, n]));

  return (
    <div className="dag-view">
      <div className="dag-head">
        <h3>DAG 执行图</h3>
        <div className="dag-meta">
          <span className="tag">{dag.nodes.length} 个节点</span>
          <span className="tag">最大并行 {dag.parallel_width}</span>
          {dag.cyclic && <span className="tag tag-clay">检测到环</span>}
        </div>
      </div>
      <div className="dag-layers">
        {layers.map((keys, li) => (
          <div className="dag-layer" key={li}>
            <div className="dag-layer-label">L{li}</div>
            <div className="dag-layer-nodes">
              {keys.map((key) => {
                const n = byKey.get(key);
                if (!n) return null;
                const st = statusBySeq.get(n.seq) ?? 'queued';
                return (
                  <div
                    className="dag-node"
                    key={key}
                    style={{ borderColor: TONE[st] ?? 'var(--line)' }}
                    title={`${n.title}（${n.agent}）\n依赖：${n.depends_on.join(', ') || '无'}`}
                  >
                    <div className="dag-node-seq">#{n.seq}</div>
                    <div className="dag-node-title">{n.title}</div>
                    <div className="dag-node-agent">{n.agent}</div>
                    {n.skill && <div className="dag-node-skill">技能 · {n.skill}</div>}
                    <div className="dag-node-status" style={{ color: TONE[st] ?? 'var(--muted)' }}>
                      {st}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      {dag.edges.length > 0 && (
        <div className="dag-edges">
          依赖边：{dag.edges.length} 条 ·{' '}
          {dag.edges
            .slice(0, 8)
            .map((e) => `${e.from} → ${e.to}`)
            .join('　')}
          {dag.edges.length > 8 ? ' …' : ''}
        </div>
      )}
    </div>
  );
}
