"""Design tokens and component classes from the Claude Design mockup (light + dark)."""
from nicegui import ui

# App icon "1c · Onda" from the design (title-bar size: tile outline stroke 3). Source of truth: packaging/icon.svg.
ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 100 100">'
    '<rect x="2" y="2" width="96" height="96" rx="22" fill="#f6f6f8" stroke="#d8dade" stroke-width="3"/>'
    '<rect x="24" y="40" width="8" height="20" rx="4" fill="#3d82d1"/>'
    '<rect x="36" y="28" width="8" height="44" rx="4" fill="#3d82d1"/>'
    '<rect x="48" y="20" width="8" height="60" rx="4" fill="#17181a"/>'
    '<rect x="60" y="32" width="8" height="36" rx="4" fill="#3d82d1"/>'
    '<rect x="72" y="42" width="8" height="16" rx="4" fill="#3d82d1"/></svg>'
)

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600'
    '&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">'
)

CSS = """
:root {
  --app: #f6f6f8; --bar: #ffffff; --panel: #f0f0f3; --field: #ffffff; --line: #e3e4e8;
  --field-border: #d8dade; --btn-border: #d0d2d7; --box-border: #a8abb2; --btn: #ffffff;
  --btn-hover: #ebecef; --row-hover: #f0f0f3; --stripe: #e8e9ec;
  --text: #1b1c1f; --text-strong: #111214; --text-2: #3a3c42; --text-btn: #2a2c31;
  --muted: #62656c; --subtle: #868991; --log: #62656c; --faint: #9a9da4; --max: #000000;
  --accent: #3d82d1; --accent-hover: #2f74c0; --on-accent: #ffffff; --link: #2a6db8;
  --accent-soft: #e2edfa; --accent-text: #1f5fa8;
  --danger-border: #efc3c3; --danger: #c23b3b; --danger-soft: #fdeeee;
  --ok-soft: #e1f4e7; --ok: #1f7a3d; --ok-bar: #3a9a5a; --amber: #8a5a00; --amber-soft: #fbf1d9;
}
:root[data-theme="dark"] {
  --app: #141517; --bar: #1a1b1e; --panel: #17181a; --field: #0f1012; --line: #26282c;
  --field-border: #2a2c31; --btn-border: #2f3136; --box-border: #45484f; --btn: #1e2023;
  --btn-hover: #25272b; --row-hover: #1b1c1f; --stripe: #202226;
  --text: #e6e7ea; --text-strong: #f2f3f5; --text-2: #c9cbd0; --text-btn: #d4d6da;
  --muted: #8a8d94; --subtle: #6b6e75; --log: #7d8088; --faint: #5d6067; --max: #ffffff;
  --accent: #5b9be0; --accent-hover: #73abe8; --on-accent: #0b1a2b; --link: #7fb2ea;
  --accent-soft: #1c2836; --accent-text: #9cc4f0;
  --danger-border: #5a2a2c; --danger: #f08a8a; --danger-soft: #2a1718;
  --ok-soft: #16301f; --ok: #7fd39a; --ok-bar: #4fae6e; --amber: #e0b45a; --amber-soft: #2b2414;
}
:root { --q-primary: var(--accent); --col-status: 132px; --col-actions: 104px; }
html, body { background: var(--app); color: var(--text); font-family: 'IBM Plex Sans', system-ui, sans-serif;
  -webkit-font-smoothing: antialiased; overflow: hidden; }
/* The page never scrolls; each region scrolls on its own (min-height: 0 on flex/grid children). */
.q-page, .nicegui-content { padding: 0; gap: 0; height: 100vh; min-height: 0 !important; overflow: hidden;
  flex-wrap: nowrap; }
.mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; }
.yt-bar { height: 52px; flex-shrink: 0; border-bottom: 1px solid var(--line); background: var(--bar); padding: 0 16px;
  display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; width: 100%; }
.yt-panel { background: var(--panel); }
.yt-line-r { border-right: 1px solid var(--line); } .yt-line-l { border-left: 1px solid var(--line); }
.yt-line-t { border-top: 1px solid var(--line); } .yt-line-b { border-bottom: 1px solid var(--line); }
.yt-label { font-size: 12px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--muted); }
.yt-muted { color: var(--muted); } .yt-subtle { color: var(--subtle); } .yt-text2 { color: var(--text-2); }
.yt-box { background: var(--field); border: 1px solid var(--field-border); border-radius: 8px; }
.yt-field { background: var(--field); border: 1px solid var(--field-border); border-radius: 7px; height: 36px;
  padding: 0 12px; box-sizing: border-box; }
.yt-field:focus-within { border-color: var(--accent); }
.yt-field .q-field__control, .yt-field .q-field__native { height: 34px; min-height: 34px; color: var(--text);
  font-family: 'IBM Plex Mono', monospace; font-size: 12px; }
.yt-field .q-field__native::placeholder { color: var(--subtle); opacity: 1; }
.yt-btn { height: 36px; padding: 0 12px; border: 1px solid var(--btn-border); background: var(--btn); color: var(--text-btn);
  font: inherit; font-size: 13px; font-weight: 500; border-radius: 7px; cursor: pointer; }
.yt-btn:hover { background: var(--btn-hover); }
.yt-primary { height: 36px; padding: 0 20px; border: 0; background: var(--accent); color: var(--on-accent);
  font: inherit; font-size: 13px; font-weight: 600; border-radius: 7px; cursor: pointer; }
.yt-primary:hover { background: var(--accent-hover); }
.yt-danger { height: 38px; padding: 0 16px; border: 1px solid var(--danger-border); background: transparent; color: var(--danger);
  font: inherit; font-size: 13px; font-weight: 500; border-radius: 7px; cursor: pointer; }
.yt-danger:hover { background: var(--danger-soft); }
button:disabled { opacity: .45; cursor: default; pointer-events: none; }
.yt-link { border: 0; background: transparent; color: var(--link); font: inherit; font-size: 12px; font-weight: 500;
  padding: 5px 8px; border-radius: 5px; cursor: pointer; white-space: nowrap; }
.yt-link:hover { background: var(--btn-hover); }
.yt-ghost { border: 0; background: transparent; color: var(--muted); border-radius: 6px; cursor: pointer; line-height: 1; }
.yt-ghost:hover { background: var(--btn-hover); color: var(--text); }
.yt-seg { display: flex; gap: 2px; padding: 3px; background: var(--field); border: 1px solid var(--field-border); border-radius: 8px; }
.yt-seg > button { border: 0; cursor: pointer; font: inherit; font-size: 13px; font-weight: 500; padding: 6px 18px;
  border-radius: 6px; background: transparent; color: var(--muted); }
.yt-seg > button.on { background: var(--field-border); color: var(--text-strong); }
.yt-seg.small { border-radius: 7px; display: grid; grid-template-columns: repeat(5, 1fr); }
.yt-seg.two { border-radius: 7px; display: grid; grid-template-columns: 1fr 1fr; }
.yt-seg.two > button { font-size: 12px; padding: 6px 0; border-radius: 5px; }
.yt-seg.small > button { font-family: 'IBM Plex Mono', monospace; font-size: 12px; padding: 6px 0; border-radius: 5px; }
.yt-toggle { border: 0; background: transparent; color: var(--muted); font: inherit; font-size: 12px; font-weight: 500;
  padding: 6px 10px; border-radius: 6px; cursor: pointer; }
.yt-toggle.on { background: var(--accent-soft); color: var(--link); }
.yt-linkrow { display: grid; grid-template-columns: 18px 64px minmax(0,1fr) 22px; gap: 8px; align-items: center;
  padding: 6px 6px 6px 8px; border-radius: 6px; background: var(--btn); border: 1px solid var(--line); }
.yt-tag { font-size: 10px; font-weight: 600; letter-spacing: .03em; text-transform: uppercase; text-align: center;
  padding: 2px 0; border-radius: 4px; background: var(--line); color: var(--muted); }
.yt-tag.list { background: var(--accent-soft); color: var(--link); }
/* Fixed right-hand columns so status chips and actions line up on every row. */
.yt-row { display: grid; grid-template-columns: 20px 64px minmax(0,1fr) var(--col-status) var(--col-actions);
  gap: 14px; align-items: center; padding: 9px 8px; border-radius: 8px; cursor: pointer; border: 1px solid transparent;
  width: 100%; box-sizing: border-box; /* rows live in a flex column; without this each row shrinks to its content */ }
/* Fixed-height rows: three fixed text lines; the third holds the progress bar or the error reason. */
.yt-row { height: 64px; }
.yt-text { display: grid; grid-template-rows: 18px 16px 12px; row-gap: 2px; min-width: 0; width: 100%; align-items: center; }
.yt-titleline { display: flex; gap: 6px; align-items: center; min-width: 0; }
.yt-title { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.yt-meta { font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.yt-third { position: relative; height: 12px; min-width: 0; display: flex; align-items: center; }
.yt-third .yt-track { width: 100%; margin: 0; }
.yt-reason { font-size: 12px; line-height: 12px; color: var(--danger); white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; min-width: 0; width: 100%; }
.yt-row.err { background: var(--danger-soft); border-color: var(--danger-border); }
.yt-row.err:hover { background: var(--danger-soft); }
.yt-row.off .dim { opacity: .5; }
.yt-row > .yt-pill { justify-self: stretch; text-align: center; padding: 4px 0; }
.yt-qhead { display: grid; grid-template-columns: 20px 64px minmax(0,1fr) var(--col-status) var(--col-actions);
  gap: 14px; padding: 0 25px 6px; font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
  color: var(--subtle); }
.yt-new { flex-shrink: 0; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em;
  padding: 1px 5px; border-radius: 4px; background: var(--accent-soft); color: var(--link); }
.yt-retry { height: 28px; border: 1px solid var(--danger-border); background: transparent; color: var(--danger);
  font: inherit; font-size: 12px; font-weight: 500; border-radius: 6px; cursor: pointer; width: 100%; }
.yt-retry:hover { background: var(--danger-soft); }
.yt-notice { display: flex; gap: 8px; align-items: flex-start; font-size: 12px; line-height: 1.45; color: var(--link);
  background: var(--accent-soft); border-radius: 6px; padding: 7px 10px; }
.yt-notice::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); margin-top: 6px; flex-shrink: 0; }
.yt-sep { height: 1px; background: var(--line); flex-shrink: 0; width: 100%; }
.yt-divider { width: 1px; height: 16px; background: var(--btn-border); margin: 0 4px; }
.yt-btn.yt-sm { height: auto; font-size: 12px; padding: 5px 10px; border-radius: 6px; }
.yt-logline { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--log); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.yt-logbox { font-family: 'IBM Plex Mono', monospace; font-size: 11px; line-height: 1.65; white-space: pre-wrap;
  word-break: break-all; background: var(--field); border: 1px solid var(--field-border); border-radius: 7px;
  padding: 10px 12px; overflow: auto; color: var(--log); }
.yt-logbox .ok { color: var(--ok); } .yt-logbox .err { color: var(--danger); } .yt-logbox .amb { color: var(--amber); }
.yt-pill.amb { background: var(--amber-soft); color: var(--amber); }
.yt-pill.line { background: var(--line); color: var(--muted); }
.yt-card { border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 2px; }
.yt-card.ok { background: var(--ok-soft); color: var(--ok); }
.yt-card.err { background: var(--danger-soft); color: var(--danger); }
.yt-card.plain { background: var(--btn); border: 1px solid var(--line); }
.yt-card.plain .k { color: var(--muted); }
.yt-failbox { border: 1px solid var(--danger-border); border-radius: 8px; overflow: hidden; }
.yt-failbox .h { padding: 8px 12px; font-size: 12px; font-weight: 600; color: var(--danger); background: var(--danger-soft); }
.yt-failbox .r { display: flex; justify-content: space-between; gap: 12px; padding: 8px 12px; border-top: 1px solid var(--line);
  font-size: 12px; }
.yt-ghostbtn { height: 36px; padding: 0 14px; border: 0; background: transparent; color: var(--muted); font: inherit;
  font-size: 13px; border-radius: 7px; cursor: pointer; }
.yt-ghostbtn:hover { background: var(--btn-hover); }
.yt-danger.yt-md { height: 36px; padding: 0 14px; }
.yt-fmt { font-size: 10px; font-weight: 600; letter-spacing: .03em; text-align: center; padding: 2px 0; border-radius: 4px;
  background: var(--accent-soft); color: var(--link); }
.yt-fmt.mp4 { background: var(--amber-soft); color: var(--amber); }
.yt-fmt.pad { padding: 2px 6px; }
.yt-videobox { position: relative; width: 100%; aspect-ratio: 16 / 9; border-radius: 10px; overflow: hidden; background: #000; }
.yt-videobox video { width: 100%; height: 100%; object-fit: contain; background: #000; }
.yt-fullbtn { position: absolute; right: 8px; bottom: 8px; height: 28px; padding: 0 10px; border: 0; border-radius: 6px;
  background: rgba(0,0,0,.65); color: #fff; font: inherit; font-size: 12px; cursor: pointer; z-index: 2; }
.yt-fullbtn:hover { background: rgba(0,0,0,.85); }
/* In-window fullscreen (works in every webview; Esc exits). */
.yt-videobox.full { position: fixed; inset: 0; z-index: 3000; width: auto; aspect-ratio: auto; border-radius: 0; }
.yt-actions { display: flex; justify-content: flex-end; align-items: center; gap: 2px; min-width: 0; }
.yt-area { background: var(--field); border: 1px solid var(--field-border); border-radius: 7px; padding: 6px 10px; }
.yt-area:focus-within { border-color: var(--accent); }
.yt-area textarea { color: var(--text); font-family: 'IBM Plex Mono', monospace; font-size: 12px; line-height: 1.5;
  resize: none; }
.yt-area textarea::placeholder { color: var(--subtle); opacity: 1; }
.yt-row:hover { background: var(--row-hover); }
.yt-check { width: 16px; height: 16px; border-radius: 4px; border: 1.5px solid var(--box-border); display: flex;
  align-items: center; justify-content: center; font-size: 11px; font-weight: 700; color: var(--on-accent); }
.yt-check.on { background: var(--accent); border-color: var(--accent); }
.yt-thumb { width: 64px; height: 36px; border-radius: 5px; border: 1px solid var(--field-border); object-fit: cover;
  background: repeating-linear-gradient(135deg, var(--stripe) 0 6px, var(--bar) 6px 12px); }
.yt-cover { aspect-ratio: 1; border-radius: 10px; border: 1px solid var(--field-border); display: flex;
  align-items: center; justify-content: center; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--faint);
  background: repeating-linear-gradient(135deg, var(--stripe) 0 10px, var(--bar) 10px 20px); }
.yt-track { height: 3px; border-radius: 2px; background: var(--line); overflow: hidden; margin-top: 3px; }
.yt-track.big { height: 4px; margin: 0; }
.yt-fill { height: 100%; width: 0; background: var(--accent); transition: width .2s; }
.yt-fill.ok { background: var(--ok-bar); } .yt-fill.err { background: var(--danger); }
.yt-pill { justify-self: end; font-size: 11px; font-weight: 500; padding: 3px 8px; border-radius: 999px;
  background: var(--btn); color: var(--muted); white-space: nowrap; }
.yt-pill.run { background: var(--accent-soft); color: var(--link); }
.yt-pill.ok { background: var(--ok-soft); color: var(--ok); }
.yt-pill.err { background: var(--danger-soft); color: var(--danger); }
.yt-log { font-family: 'IBM Plex Mono', monospace; font-size: 11px; line-height: 1.7; color: var(--log);
  background: var(--field); border: 1px solid var(--field-border); border-radius: 7px; padding: 10px 12px; }
.yt-stat.ok { color: var(--ok); } .yt-stat.err { color: var(--danger); }
.yt-error { color: var(--danger); }
.yt-modal { background: var(--bar); color: var(--text); border: 1px solid var(--btn-border); border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0,0,0,.35); max-width: none; }
.yt-libhead, .yt-librow { display: grid; grid-template-columns: 28px 40px minmax(0,1fr) 140px 56px; gap: 14px; align-items: center; }
.yt-libhead { padding: 6px 16px; margin: 0 16px; font-size: 11px; font-weight: 600; letter-spacing: .04em;
  text-transform: uppercase; color: var(--subtle); border-bottom: 1px solid var(--line); }
.yt-librow { padding: 9px 16px; border-radius: 7px; cursor: pointer; }
.yt-librow:hover { background: var(--btn); }
.yt-librow.cur { background: var(--accent-soft); }
.yt-librow.cur .t { color: var(--accent-text); } .yt-librow.cur .n { color: var(--link); }
.yt-play { width: 48px; height: 48px; border: 0; border-radius: 50%; background: var(--text); color: var(--app);
  font-size: 16px; cursor: pointer; }
.yt-play:hover { background: var(--max); }
.yt-skip { width: 40px; height: 40px; border: 0; border-radius: 50%; background: transparent; color: var(--text-2);
  font-size: 14px; cursor: pointer; }
.yt-skip:hover { background: var(--btn-hover); }
.yt-menu { background: var(--bar); border: 1px solid var(--btn-border); border-radius: 9px; padding: 6px; }
.yt-menu .q-item { color: var(--text-2); border-radius: 6px; min-height: 32px; }
"""


def apply() -> None:
    ui.add_head_html(FONTS + f"<style>{CSS}</style>")


def set_theme(dark: bool) -> None:
    ui.run_javascript(f"document.documentElement.dataset.theme = '{'dark' if dark else 'light'}'")
