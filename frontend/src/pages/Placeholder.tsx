export default function Placeholder({
  eyebrow,
  title,
  sub,
}: {
  eyebrow: string;
  title: string;
  sub: string;
}) {
  return (
    <section className="page active">
      <div className="wrap">
        <header className="page-head">
          <div className="page-head-main">
            <span className="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p className="page-sub">{sub}</p>
          </div>
        </header>
        <div className="panel">
          <div className="panel-body" style={{ paddingTop: 18 }}>
            <div className="empty-note">
              该模块不在 Phase 1（P0）范围内，当前仅保留路由与信息架构，接口随后续阶段接入。
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
