import { app } from "../../scripts/app.js";

const MEDIA_TYPES = new Set(["image", "video", "audio"]);
const SELECTION_OPTIONS = [
  ["all", "All references (legacy behavior)"],
  ["tagged_only", "Prompt tags only"],
  ["tagged_plus_untagged", "Prompt tags + untagged"],
];

let stylesInstalled = false;
function installStyles() {
  if (stylesInstalled) return;
  stylesInstalled = true;
  const style = document.createElement("style");
  style.textContent = `
    .ds-h3-tags-overlay{position:fixed;inset:0;z-index:10050;background:rgba(6,9,13,.72);display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box}
    .ds-h3-tags-panel{width:min(920px,94vw);max-height:88vh;overflow:hidden;background:#111820;border:1px solid #40515e;border-radius:10px;box-shadow:0 12px 40px #000;display:flex;flex-direction:column;color:#dbe7f0;font:13px system-ui,sans-serif}
    .ds-h3-tags-header{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;background:#0d1217;border-bottom:1px solid #344452}
    .ds-h3-tags-title{font-size:16px;font-weight:700;color:#efe6ff}.ds-h3-tags-close{font-size:18px!important;padding:1px 8px!important}
    .ds-h3-tags-body{overflow:auto;padding:12px 14px;display:flex;flex-direction:column;gap:10px}
    .ds-h3-tags-help{color:#9fb3c2;line-height:1.45}.ds-h3-tags-help code{color:#bff3d0;background:#0b1015;padding:1px 4px;border-radius:3px}
    .ds-h3-tags-mode{display:flex;gap:9px;align-items:center;flex-wrap:wrap;padding:9px;background:#0b1015;border:1px solid #344452;border-radius:6px}
    .ds-h3-tags-mode select{background:#111a21;color:#e5eef4;border:1px solid #40515e;border-radius:4px;padding:6px 8px;min-width:260px}
    .ds-h3-tags-list{display:flex;flex-direction:column;gap:7px}
    .ds-h3-tags-row{display:grid;grid-template-columns:135px minmax(170px,1fr) minmax(260px,1.35fr) 105px;gap:8px;align-items:center;padding:8px;background:#0d1217;border:1px solid #344452;border-radius:6px}
    .ds-h3-tags-kind{font-weight:700;color:#bcd9ff}.ds-h3-tags-file{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#b9c8d2}
    .ds-h3-tags-input{width:100%;box-sizing:border-box;background:#090d11;color:#e5eef4;border:1px solid #40515e;border-radius:4px;padding:6px 7px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
    .ds-h3-tags-always{display:flex;align-items:center;gap:5px;color:#c8d6df;white-space:nowrap}
    .ds-h3-tags-empty{padding:18px;text-align:center;color:#9fb3c2;border:1px dashed #40515e;border-radius:6px}
    .ds-h3-tags-footer{padding:10px 14px;background:#0d1217;border-top:1px solid #344452;display:flex;gap:7px;justify-content:flex-end}
    .ds-h3-tags-footer button,.ds-h3-tags-header button{background:#202b35;color:#dbe7f0;border:1px solid #40515e;border-radius:4px;padding:6px 10px;cursor:pointer}
    .ds-h3-tags-footer button:hover,.ds-h3-tags-header button:hover{background:#2c3c49}.ds-h3-tags-save{border-color:#57966d!important;color:#caffda!important}
    @media(max-width:760px){.ds-h3-tags-row{grid-template-columns:1fr}.ds-h3-tags-file{white-space:normal}.ds-h3-tags-mode select{min-width:0;width:100%}}
  `;
  document.head.appendChild(style);
}

function parseStateWidget(node) {
  const widget = node.widgets?.find(w => w.name === "timeline_data");
  if (!widget) return { widget: null, state: { items: [] } };
  try {
    const parsed = JSON.parse(widget.value || "{}");
    return { widget, state: parsed && typeof parsed === "object" ? parsed : { items: [] } };
  } catch {
    return { widget, state: { items: [] } };
  }
}

function currentState(node) {
  const live = node.__dasiwaH3State?.();
  if (live && typeof live === "object") return { state: live, widget: node.widgets?.find(w => w.name === "timeline_data") };
  return parseStateWidget(node);
}

function persistState(node, state, widget) {
  const dataWidget = widget || node.widgets?.find(w => w.name === "timeline_data");
  if (dataWidget) {
    dataWidget.value = JSON.stringify(state);
    dataWidget.callback?.(dataWidget.value);
  }
  node.__dasiwaH3Render?.();
  node.graph?.setDirtyCanvas?.(true, true);
}

function normalizeTags(value) {
  const raw = String(value || "").split(/[\s,;]+/).map(v => v.trim()).filter(Boolean);
  const out = [];
  const seen = new Set();
  for (let token of raw) {
    token = token.replace(/^@+/, "");
    if (!/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(token)) continue;
    const tag = `@${token}`.toLowerCase();
    if (!seen.has(tag)) { seen.add(tag); out.push(tag); }
  }
  return out;
}

function itemTags(item) {
  const source = Array.isArray(item.tags) ? item.tags.join(" ") : (item.tags || item.tag || "");
  return normalizeTags(source);
}

function mediaLabel(item, counters) {
  const kind = item.type || "ref";
  counters[kind] = (counters[kind] || 0) + 1;
  const prefix = kind === "image" ? "Picture" : kind === "video" ? "Video" : "Audio";
  const stream = kind === "video" ? ({ video: "V", audio: "A", video_audio: "V+A" }[item.media_mode || "video"] || "V") : "";
  return `${prefix} ${counters[kind]}${stream ? ` · ${stream}` : ""}`;
}

function openTagEditor(node) {
  installStyles();
  const { state, widget } = currentState(node);
  state.items ||= [];
  const media = state.items.filter(item => item && MEDIA_TYPES.has(item.type));

  const overlay = document.createElement("div");
  overlay.className = "ds-h3-tags-overlay";
  const panel = document.createElement("div"); panel.className = "ds-h3-tags-panel";
  const header = document.createElement("div"); header.className = "ds-h3-tags-header";
  const title = document.createElement("div"); title.className = "ds-h3-tags-title"; title.textContent = "🏷 MiniMax H3 Tagged References";
  const close = document.createElement("button"); close.className = "ds-h3-tags-close"; close.textContent = "×";
  header.append(title, close);

  const body = document.createElement("div"); body.className = "ds-h3-tags-body";
  const help = document.createElement("div"); help.className = "ds-h3-tags-help";
  help.innerHTML = "Assign one or more tags to each REF2VA asset, then use them directly in the Director prompt, e.g. <code>@alice</code> or <code>@car</code>. At queue time DaSiWa selects the matching media and compiles tags to native <code>&lt;Picture N&gt;</code>, <code>&lt;Video N&gt;</code>, and <code>&lt;Audio N&gt;</code> labels. Selected references are renumbered automatically.";
  body.append(help);

  const modeRow = document.createElement("div"); modeRow.className = "ds-h3-tags-mode";
  const modeLabel = document.createElement("strong"); modeLabel.textContent = "Reference selection:";
  const select = document.createElement("select");
  for (const [value, label] of SELECTION_OPTIONS) { const option = document.createElement("option"); option.value = value; option.textContent = label; select.append(option); }
  select.value = SELECTION_OPTIONS.some(([value]) => value === state.reference_selection) ? state.reference_selection : "all";
  const modeHint = document.createElement("span"); modeHint.style.color = "#9fb3c2"; modeHint.textContent = "All = backwards-compatible. Prompt tags only = Ethan-style selection.";
  modeRow.append(modeLabel, select, modeHint); body.append(modeRow);

  const list = document.createElement("div"); list.className = "ds-h3-tags-list";
  const rows = [];
  if (!media.length) {
    const empty = document.createElement("div"); empty.className = "ds-h3-tags-empty"; empty.textContent = "No image/video/audio references are currently loaded in the Director."; list.append(empty);
  } else {
    const counters = { image: 0, video: 0, audio: 0 };
    for (const item of media) {
      const row = document.createElement("div"); row.className = "ds-h3-tags-row";
      const kind = document.createElement("div"); kind.className = "ds-h3-tags-kind"; kind.textContent = mediaLabel(item, counters);
      const file = document.createElement("div"); file.className = "ds-h3-tags-file"; file.title = String(item.value || ""); file.textContent = String(item.value || "(in-memory reference)").split(/[\\/]/).pop();
      const input = document.createElement("input"); input.className = "ds-h3-tags-input"; input.type = "text"; input.placeholder = "@alice @main_character"; input.value = itemTags(item).join(" ");
      const alwaysLabel = document.createElement("label"); alwaysLabel.className = "ds-h3-tags-always";
      const always = document.createElement("input"); always.type = "checkbox"; always.checked = !!item.always_on;
      const alwaysText = document.createElement("span"); alwaysText.textContent = "Always on"; alwaysLabel.append(always, alwaysText);
      row.append(kind, file, input, alwaysLabel); list.append(row);
      rows.push({ item, input, always });
    }
  }
  body.append(list);

  const footer = document.createElement("div"); footer.className = "ds-h3-tags-footer";
  const clearBtn = document.createElement("button"); clearBtn.textContent = "Clear tags";
  const cancelBtn = document.createElement("button"); cancelBtn.textContent = "Cancel";
  const saveBtn = document.createElement("button"); saveBtn.className = "ds-h3-tags-save"; saveBtn.textContent = "Save tagged references";
  footer.append(clearBtn, cancelBtn, saveBtn);
  panel.append(header, body, footer); overlay.append(panel); document.body.append(overlay);

  const dismiss = () => overlay.remove();
  close.onclick = dismiss; cancelBtn.onclick = dismiss;
  overlay.onclick = event => { if (event.target === overlay) dismiss(); };
  const onKey = event => { if (event.key === "Escape") { dismiss(); window.removeEventListener("keydown", onKey); } };
  window.addEventListener("keydown", onKey);

  clearBtn.onclick = () => { for (const { input, always } of rows) { input.value = ""; always.checked = false; } };
  saveBtn.onclick = () => {
    state.reference_selection = select.value;
    for (const { item, input, always } of rows) {
      const tags = normalizeTags(input.value);
      if (tags.length) item.tags = tags; else delete item.tags;
      delete item.tag;
      item.always_on = !!always.checked;
      if (!item.always_on) delete item.always_on;
    }
    persistState(node, state, widget);
    dismiss();
  };
}

function install(node) {
  if (!node || node.comfyClass !== "MiniMaxH3Director" || node.__dasiwaTaggedRefsInstalled) return;
  node.__dasiwaTaggedRefsInstalled = true;

  const oldMenu = node.getExtraMenuOptions;
  node.getExtraMenuOptions = function (canvas, options) {
    const result = oldMenu?.call(this, canvas, options);
    if (Array.isArray(options)) {
      options.push(null, {
        content: "🏷 Tagged References…",
        callback: () => openTagEditor(node),
      });
    }
    return result;
  };

  // Keep a callable hook for other DaSiWa UI code and for debugging.
  node.__dasiwaOpenTaggedReferences = () => openTagEditor(node);
}

app.registerExtension({
  name: "DaSiWa.MiniMaxH3TaggedReferences",
  nodeCreated(node) { install(node); },
  loadedGraphNode(node) { install(node); },
});
