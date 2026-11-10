// 由原型 sprite 抽取，保持 <use href="#i-xxx"> 的用法不变
export default function Sprite() {
  return (
    <svg className="sprite" aria-hidden="true">

  <symbol id="i-spark" viewBox="0 0 24 24"><path d="M12 3l1.9 5.4L19 10l-5.1 1.6L12 17l-1.9-5.4L5 10l5.1-1.6z"/><path d="M18.5 16.5l.7 2 1.8.7-1.8.7-.7 2-.7-2-1.8-.7 1.8-.7z"/></symbol>
  <symbol id="i-chat" viewBox="0 0 24 24"><path d="M4.5 6.5a2.5 2.5 0 012.5-2.5h10a2.5 2.5 0 012.5 2.5v7a2.5 2.5 0 01-2.5 2.5H10l-4.2 3.2a.6.6 0 01-.8-.6z"/></symbol>
  <symbol id="i-send" viewBox="0 0 24 24"><path d="M4.5 12l15-7-4.2 14-3.3-5.3z"/><path d="M12 13.7L19.5 5"/></symbol>
  <symbol id="i-image" viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="14" rx="2.5"/><circle cx="9" cy="10" r="1.6"/><path d="M5 17l4.5-4.5 3.5 3 3-2.5 3 4"/></symbol>
  <symbol id="i-paper" viewBox="0 0 24 24"><path d="M19 12.5V18a2 2 0 01-2 2H7a2 2 0 01-2-2V6a2 2 0 012-2h5.5"/><path d="M15 3.5l5 5H16a1 1 0 01-1-1z"/></symbol>
  <symbol id="i-home" viewBox="0 0 24 24"><path d="M4 10.5L12 4l8 6.5"/><path d="M6.5 9.5V19h11V9.5"/><path d="M10 19v-4.5h4V19"/></symbol>
  <symbol id="i-tasks" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 9.5h4M8 14h8M14.5 9.5H16"/></symbol>
  <symbol id="i-people" viewBox="0 0 24 24"><circle cx="9" cy="8.5" r="3"/><path d="M3.5 19c.6-3.1 2.9-5 5.5-5s4.9 1.9 5.5 5"/><circle cx="17" cy="10" r="2.4"/><path d="M15.5 19c.3-2.4 1.6-4 3.5-4 1.2 0 2.3.6 3 1.6"/></symbol>
  <symbol id="i-folder" viewBox="0 0 24 24"><path d="M3.5 7.5a2 2 0 012-2h3.2l1.8 2h8a2 2 0 012 2v8a2 2 0 01-2 2h-13a2 2 0 01-2-2z"/></symbol>
  <symbol id="i-shield" viewBox="0 0 24 24"><path d="M12 3.5l7 2.6v5.4c0 4.3-2.9 7.6-7 9-4.1-1.4-7-4.7-7-9V6.1z"/><path d="M9 12l2 2 4-4"/></symbol>
  <symbol id="i-memory" viewBox="0 0 24 24"><path d="M8.5 4.5h7A2.5 2.5 0 0118 7v10a2.5 2.5 0 01-2.5 2.5h-7A2.5 2.5 0 016 17V7a2.5 2.5 0 012.5-2.5z"/><path d="M9.5 9h5M9.5 12.5h5M9.5 16h3"/></symbol>
  <symbol id="i-cpu" viewBox="0 0 24 24"><rect x="6.5" y="6.5" width="11" height="11" rx="2"/><path d="M9.5 10h5v4h-5z"/><path d="M10 3.5V6.5M14 3.5V6.5M10 17.5v3M14 17.5v3M3.5 10h3M3.5 14h3M17.5 10h3M17.5 14h3"/></symbol>
  <symbol id="i-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
  <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M15.8 15.8L20 20"/></symbol>
  <symbol id="i-chev-down" viewBox="0 0 24 24"><path d="M6 9.5l6 6 6-6"/></symbol>
  <symbol id="i-arrow-right" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></symbol>
  <symbol id="i-back" viewBox="0 0 24 24"><path d="M19 12H5M11 6l-6 6 6 6"/></symbol>
  <symbol id="i-play" viewBox="0 0 24 24"><path d="M8 5.5l11 6.5-11 6.5z"/></symbol>
  <symbol id="i-pause" viewBox="0 0 24 24"><path d="M9 5.5v13M15 5.5v13"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7"/></symbol>
  <symbol id="i-x" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></symbol>
  <symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/></symbol>
  <symbol id="i-alert" viewBox="0 0 24 24"><path d="M12 4l8.5 15H3.5z"/><path d="M12 9.5v4M12 16.5v.01"/></symbol>
  <symbol id="i-list" viewBox="0 0 24 24"><path d="M8 7h12M8 12h12M8 17h12M4 7h.01M4 12h.01M4 17h.01"/></symbol>
  <symbol id="i-board" viewBox="0 0 24 24"><rect x="3.5" y="5" width="5" height="14" rx="1.5"/><rect x="9.75" y="5" width="5" height="10" rx="1.5"/><rect x="16" y="5" width="4.5" height="7" rx="1.5"/></symbol>
  <symbol id="i-file" viewBox="0 0 24 24"><path d="M6.5 3.5h7l4 4v13h-11z"/><path d="M13.5 3.5v4h4"/></symbol>
  <symbol id="i-download" viewBox="0 0 24 24"><path d="M12 4v10M7.5 10l4.5 4.5L16.5 10"/><path d="M5 19h14"/></symbol>
  <symbol id="i-bag" viewBox="0 0 24 24"><rect x="4.5" y="7.5" width="15" height="12" rx="2.5"/><path d="M9 7.5V6a3 3 0 016 0v1.5"/></symbol>
  <symbol id="i-tool" viewBox="0 0 24 24"><path d="M14.5 4.5a4.5 4.5 0 00-5.7 5.7L4 15v5h5l4.8-4.8a4.5 4.5 0 005.7-5.7l-3 3-2-2z"/></symbol>
  <symbol id="i-plug" viewBox="0 0 24 24"><path d="M9 4v5M15 4v5"/><path d="M6.5 9h11v2.5a5.5 5.5 0 01-11 0z"/><path d="M12 17v3.5"/></symbol>
  <symbol id="i-refresh" viewBox="0 0 24 24"><path d="M19 12a7 7 0 10-2.6 5.4"/><path d="M19.5 4.5v5h-5"/></symbol>
  <symbol id="i-more" viewBox="0 0 24 24"><path d="M6 12h.01M12 12h.01M18 12h.01"/></symbol>
  <symbol id="i-spark2" viewBox="0 0 24 24"><path d="M12 3.5l2.1 6.4 6.4 2.1-6.4 2.1L12 20.5l-2.1-6.4L3.5 12l6.4-2.1z"/></symbol>
  <symbol id="i-filter" viewBox="0 0 24 24"><path d="M4 6h16M7 12h10M10 18h4"/></symbol>
  <symbol id="i-branch" viewBox="0 0 24 24"><circle cx="7" cy="5.5" r="2.5"/><circle cx="7" cy="18.5" r="2.5"/><circle cx="17" cy="10" r="2.5"/><path d="M7 8v8M9.5 10.5h5"/></symbol>
  <symbol id="i-settings" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3.2"/><path d="M12 4.2v2.1M12 17.7v2.1M4.2 12h2.1M17.7 12h2.1M6.6 6.6l1.5 1.5M15.9 15.9l1.5 1.5M17.4 6.6l-1.5 1.5M8.1 15.9l-1.5 1.5"/></symbol>
  <symbol id="i-logout" viewBox="0 0 24 24"><path d="M14 5h4.4A1.6 1.6 0 0120 6.6v10.8A1.6 1.6 0 0118.4 19H14"/><path d="M10 8.5L6.5 12l3.5 3.5M6.5 12H15"/></symbol>
  <symbol id="i-close" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></symbol>
  <symbol id="i-book" viewBox="0 0 24 24"><path d="M5 5.4A2.4 2.4 0 017.4 3H19v15.4H7.4A2.4 2.4 0 005 20.8V5.4z"/><path d="M5 18.2A2.4 2.4 0 017.4 15.8H19"/></symbol>
  <symbol id="i-expand" viewBox="0 0 24 24"><path d="M9 4H4v5M15 4h5v5M20 15v5h-5M4 15v5h5"/></symbol>
  <symbol id="i-collapse" viewBox="0 0 24 24"><path d="M4 9h5V4M20 9h-5V4M15 20v-5h5M9 20v-5H4"/></symbol>
    </svg>
  );
}
