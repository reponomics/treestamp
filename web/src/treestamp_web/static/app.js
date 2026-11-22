// Preview and editor page. Talks to /api/preview and /api/op; renders text as text, never HTML.
// Decisions that need no DOM live in logic.js and are tested with node --test.

import { EXAMPLES } from "./example.js";
import { EntryFlow } from "./entry-flow.js";
import { NotePlacement } from "./placement.js";
import { saveDraft, draftForLocation } from "./draft.js";
import {
  DEFAULT_DOCUMENT,
  addressFor,
  displayPath,
  pathKey,
  hintFor,
  opBody,
  parseRoute,
  previewParams,
  preparePreview,
  regionSegments,
  rowName,
  rowSuffix,
  settingsFromValues,
  treeNavigation,
  valuesFromQuery,
  valuesFromSettings,
} from "./logic.js";

const form = document.getElementById("form");
const fields = {
  url: document.getElementById("url"),
  style: document.getElementById("style"),
  root: document.getElementById("root"),
  show_counts: document.getElementById("show_counts"),
  attribution: document.getElementById("attribution"),
  document: document.getElementById("document"),
};
const submit = document.getElementById("submit");
const visitRepo = document.getElementById("visit-repo");
const status = document.getElementById("status");
const errorPanel = document.getElementById("error");
const errorMessage = document.getElementById("error-message");
const errorHint = document.getElementById("error-hint");
document.getElementById("error-dismiss").addEventListener("click", (event) => {
  const restoreFocus = document.activeElement === event.currentTarget;
  errorPanel.hidden = true;
  if (restoreFocus) submit.focus({ preventScroll: true });
});
const repoInfo = document.getElementById("repo-info");
const repoTooltip = document.getElementById("repo-tooltip");
const repoInfoDialog = document.getElementById("repo-info-dialog");
const loadedNote = document.getElementById("loaded-note");
const settingsPanel = document.getElementById("settings");
const tabs = { editor: document.getElementById("tab-editor"), stamp: document.getElementById("tab-stamp"), info: document.getElementById("tab-info") };
const panels = { editor: document.getElementById("editor-panel"), stamp: document.getElementById("stamp-panel"), info: document.getElementById("info-panel") };
const tabNames = Object.keys(tabs);
const stage = document.getElementById("result");
let generation = 0; // responses from an older request generation are ignored
const rowsList = document.getElementById("rows");
const reveal = document.getElementById("reveal");
const revealLabel = document.getElementById("reveal-label");
const showAll = document.getElementById("show-all");
const notice = document.getElementById("notice");
const noticeText = document.getElementById("notice-text");
const noticeUndo = document.getElementById("notice-undo");
const region = document.getElementById("region");
const copy = document.getElementById("copy");
const copyLabel = document.getElementById("copy-label");
const copyStatus = document.getElementById("copy-status");
const stageStatus = document.getElementById("stage-status");
const tuiMode = document.getElementById("tui-mode");
const keymapDialog = document.getElementById("keymap-dialog");
const noteDialog = document.getElementById("note-dialog");
const noteText = document.getElementById("note-text");
const noteSave = document.getElementById("note-save");
const noteCancel = document.getElementById("note-cancel");

const placement = new NotePlacement();

let controller = null;
let countdown = null;
// The editing session: identity of the commit plus the state the server hands back.
let editor = null;
let editingSession = 0;
let userEdited = false;
const exampleContext = document.getElementById("example-context");

// ---------- settings <-> form

function formValues() {
  return {
    style: fields.style.value,
    show_counts: fields.show_counts.checked,
    attribution: fields.attribution.checked,
    root: fields.root.value,
    document: fields.document.value,
  };
}

function settingsParams() {
  return previewParams(formValues());
}

function settingsFromForm(base) {
  return settingsFromValues(base, formValues());
}

function setValues(values) {
  if ("style" in values) fields.style.value = values.style;
  if ("show_counts" in values) fields.show_counts.checked = values.show_counts;
  if ("attribution" in values) fields.attribution.checked = values.attribution;
  if ("root" in values) fields.root.value = values.root;
  if ("document" in values) fields.document.value = values.document;
}

function showSettings(data, preserveSource) {
  const values = valuesFromSettings(data.state.curation.settings);
  if (preserveSource) delete values.root;
  else values.document = displayPath(data.document);
  setValues(values);
}

// ---------- status and errors

function setBusy(busy, opening) {
  rowsList.setAttribute("aria-busy", String(busy));
  if (!opening) return;
  status.classList.toggle("busy", busy);
  if (busy) {
    submit.disabled = true;
    status.textContent = "Loading…";
    stageStatus.textContent = "Loading…";
  } else if (!countdown) {
    submit.disabled = false;
    status.textContent = "";
    stageStatus.textContent = "";
  }
}

function clearCountdown() {
  if (countdown) {
    clearInterval(countdown);
    countdown = null;
    if (!status.classList.contains("busy")) {
      submit.disabled = false;
      status.textContent = "";
    }
  }
}

function showError(message, hint, retryAfter) {
  errorMessage.textContent = message;
  errorHint.textContent = hint || "";
  errorPanel.hidden = false;
  if (!document.getElementById("entry").hidden) entryFlow.showError(message, hint);
  const dialogError = document.querySelector("dialog[open] .dialog-error");
  if (dialogError) {
    dialogError.textContent = [message, hint].filter(Boolean).join(" ");
    dialogError.hidden = false;
  }
  clearCountdown();
  if (retryAfter) {
    let remaining = retryAfter;
    submit.disabled = true;
    const tick = () => {
      status.textContent = `Retry in ${remaining}s`;
      if (remaining <= 0) {
        clearCountdown();
        submit.disabled = false;
        status.textContent = "";
      }
      remaining -= 1;
    };
    tick();
    countdown = setInterval(tick, 1000);
  }
}

// ---------- rendering

function treeRowElements(rows) {
  // Only visible siblings keep a branch open; collapsed/hidden descendants
  // should not leave dangling guide lines in the editor.
  const hasNextSibling = rows.map(() => false);
  const previousAtDepth = [];
  rows.forEach((row, index) => {
    previousAtDepth.length = row.depth + 1;
    const previous = previousAtDepth[row.depth];
    if (previous !== undefined) hasNextSibling[previous] = true;
    previousAtDepth[row.depth] = index;
  });
  const trail = [];
  return rows.map((row, index) => {
    trail.length = row.depth;
    if (row.depth) trail[row.depth - 1] = hasNextSibling[index];
    const guides = trail.map((continues, level) => {
      if (level === row.depth - 1) return continues ? "branch" : "branch last";
      return continues ? "trunk" : "";
    });
    return rowElement(row, guides);
  });
}

function rowElement(row, guides) {
  const item = document.createElement("li");
  item.className = `row ${row.kind === "dir" ? "dir" : "leaf"}${row.hidden ? " hidden-row" : ""}`;
  item.dataset.path = row.path;
  // Clicking or tapping a row focuses it, which is what reveals its actions where there
  // is no pointer to hover with. Controls inside the row keep the focus they take.
  item.tabIndex = row.path === "" ? 0 : -1;
  item.addEventListener("click", (event) => {
    if (event.target.closest("button, input, .row-actions")) return;
    item.focus({ preventScroll: true });
    if (canFold && window.getSelection().isCollapsed) operate("toggle", row.path);
  });
  for (const guide of guides) {
    const indent = document.createElement("span");
    indent.className = `indent ${guide}`;
    indent.setAttribute("aria-hidden", "true");
    item.appendChild(indent);
  }

  const canFold = row.kind === "dir" && row.path !== "";
  const name = document.createElement(canFold ? "button" : "span");
  name.className = canFold ? "name fold" : "name";
  name.textContent = rowName(row);
  if (canFold) {
    name.type = "button";
    name.dataset.action = "fold";
    name.setAttribute("aria-label", row.collapsed ? `Open ${row.name}` : `Close ${row.name}`);
    name.setAttribute("aria-expanded", String(!row.collapsed));
    name.addEventListener("click", () => {
      name.focus({ preventScroll: true });
      operate("toggle", row.path);
    });
  }
  item.appendChild(name);

  if (rowSuffix(row)) item.appendChild(Object.assign(document.createElement("span"), { className: "target", textContent: rowSuffix(row) }));
  if (row.kind === "dir" && row.collapsed && row.counts) item.appendChild(Object.assign(document.createElement("span"), { className: "counts", textContent: row.counts }));
  if (row.annotation) item.appendChild(Object.assign(document.createElement("span"), { className: "note", textContent: `# ${row.annotation}` }));

  const actions = document.createElement("span");
  actions.className = "row-actions";
  const note = document.createElement("button");
  note.type = "button";
  note.dataset.action = "note";
  note.textContent = "Note";
  note.addEventListener("click", () => enqueueEdit((saved) => {
    const current = editor.rows.find((entry) => entry.path === row.path);
    if (current && !document.querySelector("dialog[open]")) editAnnotation(current, "note");
    return saved;
  }));
  actions.appendChild(note);
  const hide = document.createElement("button");
  hide.type = "button";
  hide.dataset.action = "visibility";
  hide.textContent = row.hidden ? "Unhide" : "Hide";
  hide.disabled = row.path === "";
  if (hide.disabled) hide.title = "The root is always included";
  hide.addEventListener("click", () => {
    if (row.hidden) { operate("unhide", row.path); return; }
    operate("hide", row.path).then((ok) => { if (ok) showNotice(`Hidden ${rowName(row)}`, row.path); });
  });
  actions.appendChild(hide);
  item.appendChild(actions);
  return item;
}

let noteEditing = null;

function restoreTreeFocus(path, action) {
  const row = Array.from(rowsList.children).find((item) => item.dataset.path === path);
  const control = action && row?.querySelector(`button[data-action="${action}"]:not(:disabled)`);
  (control || row)?.focus({ preventScroll: true });
}

function editAnnotation(row, action) {
  noteEditing = { path: row.path, original: row.annotation || "", action, session: editingSession, saving: false, request: null, savedBefore: undefined };
  document.getElementById("note-path").textContent = displayPath(row.identity) || "./";
  document.getElementById("note-error").hidden = true;
  noteText.value = noteEditing.original;
  noteText.readOnly = false;
  noteSave.disabled = false;
  noteCancel.disabled = false;
  noteDialog.returnValue = "";
  restoreTreeFocus(row.path, action);
  noteDialog.showModal();
  noteText.focus();
  noteText.select();
}

async function saveAnnotation(event) {
  event.preventDefault();
  const edit = noteEditing;
  if (!edit || edit.saving) return;
  if (noteText.value === edit.original) { noteDialog.close("cancel"); return; }
  edit.saving = true;
  noteText.readOnly = true;
  noteSave.disabled = true;
  noteCancel.disabled = true;
  document.getElementById("note-error").hidden = true;
  const text = noteText.value;
  edit.request = enqueueEdit((saved) => {
    edit.savedBefore ??= saved;
    return sendOperation("annotate", edit.path, text);
  });
  const ok = await edit.request;
  if (noteEditing !== edit) return;
  edit.saving = false;
  noteText.readOnly = false;
  noteSave.disabled = false;
  noteCancel.disabled = false;
  if (ok) noteDialog.close("saved");
  else noteText.focus();
}

document.getElementById("note-form").addEventListener("submit", saveAnnotation);
noteText.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.isComposing) event.preventDefault();
});
noteCancel.addEventListener("click", () => noteDialog.close("cancel"));
noteDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  if (!noteEditing?.saving) noteDialog.close("cancel");
});
noteDialog.addEventListener("close", () => {
  if (noteDialog.open) return;
  const edit = noteEditing;
  noteEditing = null;
  if (!edit || edit.session !== editingSession) return;
  // Cancelling a failed note discards only that attempt's queue failure.
  if (noteDialog.returnValue === "cancel" && edit.request && queue === edit.request) enqueueEdit(() => edit.savedBefore);
  // Native close may already have restored focus. Do not steal it back if the
  // user has moved elsewhere before this queued close event is delivered.
  if (document.activeElement === document.body || noteDialog.contains(document.activeElement)) restoreTreeFocus(edit.path, edit.action);
});

function renderRows(rows) {
  const pagePosition = { left: window.scrollX, top: window.scrollY };
  const scroller = rowsList.parentElement;
  const treePosition = { left: scroller.scrollLeft, top: scroller.scrollTop };
  const focused = document.activeElement;
  const focusedRow = focused.closest(".row");
  const path = focusedRow?.dataset.path;
  const action = focused.dataset.action;
  const index = Array.from(rowsList.children).indexOf(focusedRow);
  rowsList.replaceChildren(...treeRowElements(rows));
  if (index >= 0) {
    const replacement = Array.from(rowsList.children).find((row) => row.dataset.path === path)
      || rowsList.children[Math.min(index, rowsList.children.length - 1)];
    if (replacement) {
      // Keep the row or control that held focus before the re-render.
      const target = action ? replacement.querySelector(`button[data-action="${action}"]:not(:disabled)`) : null;
      (target || replacement).focus({ preventScroll: true });
    }
  }
  // WebKit can scroll while replacing a focused row even with preventScroll.
  // Capture at render time so scrolling during a pending request is respected.
  scroller.scrollTo(treePosition);
  window.scrollTo(pagePosition);
}

function render(data, opening = false) {
  const prepared = preparePreview(data, window.location.origin);
  errorPanel.hidden = true;
  document.querySelectorAll(".dialog-error").forEach((node) => { node.hidden = true; });
  clearCountdown();
  const previous = editor;
  editor = {
    owner: data.repository.owner,
    repo: data.repository.name,
    ref: data.ref.commit,
    root: data.root,
    document: data.document,
    state: data.state,
    rows: prepared.rows,
    revealed: reveal.checked,
    dirty: data.dirty,
    loaded: data.loaded,
    region: data.region,
  };
  showSettings(data, !opening && Boolean(previous?.rows.length));
  document.getElementById("tree-document").textContent = displayPath(data.document);
  document.querySelector(".caption-label").textContent = data.document ? "treestamp for " : "treestamp";
  document.querySelector(".canvas-caption").classList.toggle("no-document", !data.document);
  loadedNote.textContent = data.loaded ? "Document opened" : "";
  loadedNote.hidden = !data.loaded;
  stageStatus.textContent = opening && data.loaded
    ? (data.dirty ? "Treestamp updated" : "Treestamp is up to date") : "";
  status.textContent = "";
  if (opening) {
    editingSession += 1;
    queue = Promise.resolve(true);
    userEdited = false;
  }

  document.querySelectorAll("[data-repo-branch]").forEach((node) => { node.textContent = data.repository.default_branch || "Unavailable"; });
  document.querySelectorAll("[data-repo-commit]").forEach((node) => { node.textContent = data.ref.commit; });
  visitRepo.href = data.repository.url;
  visitRepo.hidden = false;

  const address = prepared.address;
  repoInfo.disabled = false;
  document.getElementById("reset-tree").disabled = false;
  document.getElementById("active-repository").textContent = `${editor.owner}/${editor.repo}`;
  fields.url.value = `${editor.owner}/${editor.repo}`;

  renderRows(editor.rows);
  document.getElementById("tree-attribution").hidden = !data.state.curation.settings.attribution;

  renderRegion(data.region);
  copy.disabled = false;
  copyLabel.textContent = "Copy treestamp";
  setCopyStatus("");
  copy.classList.remove("copied");
  notice.hidden = true;
  const hiddenCount = data.state.curation.hidden.length;
  revealLabel.textContent = hiddenCount ? `Reveal hidden entries (${hiddenCount})` : "Reveal hidden entries";
  showAll.disabled = hiddenCount === 0;
  document.body.classList.remove("no-tree");
  history.replaceState(null, "", address);
  saveDraft(address);
}

// The marker and config lines are shown quietly so the tree reads first; the text is unchanged.
function renderRegion(text) {
  region.replaceChildren(...regionSegments(text).map((segment) => {
    const span = document.createElement("span");
    if (segment.quiet) span.className = "quiet";
    span.textContent = segment.text;
    return span;
  }));
}

// A one-line confirmation under the tree with a way back, for changes that remove a row.
let noticePath = null;
function showNotice(text, undoPath) {
  noticeText.textContent = text;
  noticePath = undoPath;
  noticeUndo.hidden = undoPath === null;
  notice.hidden = false;
}
noticeUndo.addEventListener("click", async () => {
  if (noticePath === null || noticeUndo.getAttribute("aria-disabled") === "true") return;
  const path = noticePath;
  const session = editingSession;
  let restoreFocus = document.activeElement === noticeUndo;
  const trackFocus = (event) => { if (event.target !== noticeUndo) restoreFocus = false; };
  document.addEventListener("focusin", trackFocus);
  // Keep the focused action present while saving, and available again on failure.
  noticeUndo.setAttribute("aria-disabled", "true");
  try {
    const saved = await operate("unhide", path);
    if (!saved || session !== editingSession || !restoreFocus) return;
    const restored = Array.from(rowsList.children).find((row) => row.dataset.path === path);
    restored?.focus({ preventScroll: true });
    restored?.scrollIntoView({ block: "nearest", inline: "nearest" });
  } finally {
    document.removeEventListener("focusin", trackFocus);
    noticeUndo.removeAttribute("aria-disabled");
  }
});

// A first load failed and there is no tree to keep showing.
function leaveStage() {
  stageStatus.textContent = "No tree";
}

// ---------- requests

async function acceptResponse(body, opening, editing, ticket) {
  try {
    preparePreview(body, window.location.origin);
    if (opening && body.placement?.total > 0) body = await placement.run(body);
    if (!body || ticket !== generation) return false;
    if (editing) userEdited = true;
    if (opening) exampleContext.hidden = true;
    else if (body.state?.revision > 0) userEdited = true;
    render(body, opening);
    if (opening && body.placement?.placed_count > 0) userEdited = true;
    return true;
  } catch (err) {
    showError("The page could not display the tree.", String(err && err.message), null);
    return false;
  }
}

function rejectResponse(body, responseStatus) {
  if (!editor?.rows.length) leaveStage();
  const error = (body && body.error) || {};
  const message = error.message || `The service returned status ${responseStatus}.`;
  showError(message, hintFor(error.code, responseStatus), error.retry_after || null);
  return false;
}

// Previews abort whatever is in flight. Operations never abort: each one waits for the
// previous response so it carries the newest state, which is what keeps notes from being lost.
async function call(url, init, { abortable, editing = false }) {
  placement.cancel();
  if (controller) controller.abort();
  const mine = new AbortController();
  if (abortable) controller = mine;
  const ticket = ++generation;
  setBusy(true, abortable);
  let response = null;
  let body = null;
  try {
    response = await fetch(url, { ...init, signal: abortable ? mine.signal : undefined });
    try { body = await response.json(); } catch (_) { body = null; }
  } catch (err) {
    if (mine.signal.aborted || ticket !== generation) return false;
    setBusy(false, abortable);
    if (!editor?.rows.length) leaveStage();
    showError("Could not reach the service.", "Check your connection and try again.", null);
    return false;
  }
  if (mine.signal.aborted || ticket !== generation) return false;
  setBusy(false, abortable);
  if (response.ok && body) return acceptResponse(body, abortable, editing, ticket);
  return rejectResponse(body, response.status);
}

async function preview(params) {
  const session = editingSession;
  await queue;
  if (session !== editingSession) return false;
  if (params instanceof URLSearchParams) return call(`/api/preview?${params}`, {}, { abortable: true });
  return call("/api/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params) }, { abortable: true });
}

let queue = Promise.resolve(true);

function enqueueEdit(action) {
  const session = editingSession;
  queue = queue.then((saved) => {
    if (!editor || session !== editingSession) return false;
    return action(saved);
  });
  return queue;
}

async function sendOperation(type, path, text) {
  const accepted = editor;
  const body = opBody(editor, settingsFromForm(editor.state.curation.settings), reveal.checked, type, path, text);
  const saved = await call("/api/op", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, { abortable: false, editing: type !== "restore" });
  if (!saved && editor === accepted) {
    fields.style.value = accepted.state.curation.settings.style;
    fields.show_counts.checked = accepted.state.curation.settings.show_counts;
    fields.attribution.checked = Boolean(accepted.state.curation.settings.attribution);
    reveal.checked = Boolean(accepted.revealed);
  }
  return saved;
}

function operate(type, path, text) {
  return enqueueEdit(() => sendOperation(type, path, text));
}

async function waitForEdits() {
  let pending;
  do {
    pending = queue;
    await pending;
  } while (pending !== queue);
  return pending;
}

// ---------- wiring

function isDialogBackdrop(event, dialog) {
  if (event.target !== dialog) return false;
  const bounds = dialog.getBoundingClientRect();
  return event.clientX < bounds.left || event.clientX > bounds.right
    || event.clientY < bounds.top || event.clientY > bounds.bottom;
}

for (const dialog of document.querySelectorAll("dialog")) {
  let startedOutside = false;
  dialog.addEventListener("pointerdown", (event) => {
    startedOutside = event.button === 0 && isDialogBackdrop(event, dialog);
  });
  dialog.addEventListener("pointercancel", () => { startedOutside = false; });
  dialog.addEventListener("close", () => { startedOutside = false; });
  dialog.addEventListener("click", (event) => {
    const dismiss = startedOutside && isDialogBackdrop(event, dialog);
    startedOutside = false;
    if (!dismiss) return;
    // Follow Escape's cancellation path, including pending-save/load guards.
    const accepted = dialog.dispatchEvent(new Event("cancel", { cancelable: true }));
    if (accepted && dialog.open) dialog.close("cancel");
  });
}

let repoTooltipKeyboardFocus = false;
let repoTooltipRestoringFocus = false;

function showRepoTooltip() {
  if (!repoInfo.disabled && !repoInfoDialog.open) repoTooltip.hidden = false;
}
repoInfo.addEventListener("pointerenter", (event) => {
  if (event.pointerType !== "touch") showRepoTooltip();
});
repoInfo.addEventListener("pointerdown", () => { repoTooltipKeyboardFocus = false; });
repoInfo.addEventListener("focus", () => {
  // Restored modal focus is not a new request to display the tooltip.
  if (repoTooltipRestoringFocus) {
    repoTooltipRestoringFocus = false;
    return;
  }
  repoTooltipKeyboardFocus = repoInfo.matches(":focus-visible");
  if (repoTooltipKeyboardFocus) showRepoTooltip();
});
repoInfo.addEventListener("blur", () => {
  repoTooltipKeyboardFocus = false;
  if (!repoTooltip.matches(":hover")) repoTooltip.hidden = true;
});
repoInfo.parentElement.addEventListener("pointerleave", () => {
  if (!repoTooltipKeyboardFocus) repoTooltip.hidden = true;
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !repoTooltip.hidden) {
    repoTooltip.hidden = true;
    event.preventDefault();
  }
});
repoInfo.addEventListener("click", () => {
  repoTooltipKeyboardFocus = false;
  repoInfo.focus({ preventScroll: true });
  repoTooltipRestoringFocus = true;
  repoTooltip.hidden = true;
  repoInfoDialog.showModal();
});
repoInfoDialog.addEventListener("close", () => {
  repoTooltipRestoringFocus = false;
  if (!repoTooltipKeyboardFocus) repoTooltip.hidden = true;
});

const treeKeys = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown", " "]);
const commandKeys = new Set(["a", "h", "H", "S", "f", "?"]);
let tuiEnabled = false;

tuiMode.addEventListener("click", () => {
  tuiEnabled = !tuiEnabled;
  tuiMode.setAttribute("aria-pressed", String(tuiEnabled));
});
document.getElementById("tui-help").addEventListener("click", (event) => {
  event.currentTarget.focus({ preventScroll: true });
  keymapDialog.showModal();
});

function isRowNavigationTarget(target) {
  return rowsList.contains(target) && !target.closest("input, textarea, select, [contenteditable]");
}

function navigateTree(key, saved) {
  // Resolve focus and expansion after earlier edits finish. Only apply keys while
  // focus is in the tree; note fields keep their native caret keys.
  const focused = document.activeElement;
  if (!isRowNavigationTarget(focused)) return saved;
  const item = focused.closest(".row");
  const index = editor.rows.findIndex((row) => row.path === item?.dataset.path);
  if (index < 0) return saved;
  const pane = rowsList.parentElement.getBoundingClientRect();
  const visibleHeight = Math.min(pane.bottom, window.innerHeight) - Math.max(pane.top, 0);
  const pageSize = Math.max(1, Math.floor(visibleHeight / item.getBoundingClientRect().height) - 1);
  const next = treeNavigation(editor.rows, editor.state.curation.expanded.map(pathKey), index, key, pageSize);
  if (next.operation) return sendOperation(next.operation, item.dataset.path);
  const target = rowsList.children[next.index];
  target.focus({ preventScroll: true });
  target.scrollIntoView({ block: "nearest", inline: "nearest" });
  // Moving the selection must not clear a failed edit before the next Copy.
  return saved;
}

function treeCommandContext() {
  if (!tuiEnabled || document.querySelector("dialog[open]")) return null;
  const focused = document.activeElement;
  if (!isRowNavigationTarget(focused)) return null;
  const path = focused.closest(".row")?.dataset.path;
  const row = editor.rows.find((entry) => entry.path === path);
  return row ? { focused, row } : null;
}

function runTreeCommand(key, saved) {
  const context = treeCommandContext();
  if (!context) return saved;
  const { focused, row } = context;
  if (treeKeys.has(key)) return navigateTree(key, saved);
  if (key === "a") { editAnnotation(row, focused.dataset.action); return saved; }
  if (key === "?") { keymapDialog.showModal(); return saved; }
  if (key === "S") return sendOperation("unhide_all");
  if (key === "H") {
    reveal.checked = !reveal.checked;
    return sendOperation("restore");
  }
  if (key === "f") {
    cycleCounts();
    return sendOperation("present");
  }
  if (!row.path) return saved;
  return toggleRowVisibility(row);
}

function toggleRowVisibility(row) {
  return sendOperation(row.hidden ? "unhide" : "hide", row.path).then((ok) => {
    if (ok && !row.hidden) showNotice(`Hidden ${rowName(row)}`, row.path);
    return ok;
  });
}

function cycleCounts() {
  fields.show_counts.checked = !fields.show_counts.checked;
}

function isTreeShortcut(event) {
  if (event.altKey || event.ctrlKey || event.metaKey) return false;
  if (event.shiftKey && !["H", "S", "?"].includes(event.key)) return false;
  return treeKeys.has(event.key) || commandKeys.has(event.key);
}

rowsList.addEventListener("keydown", (event) => {
  if (!tuiEnabled || event.defaultPrevented || event.isComposing) return;
  if (!isTreeShortcut(event) || !isRowNavigationTarget(event.target)) return;
  // Space on a button still activates that button.
  if (event.key === " " && event.target.closest("button")) return;
  event.preventDefault();
  if (event.repeat && commandKeys.has(event.key)) return;
  enqueueEdit((saved) => runTreeCommand(event.key, saved));
});

const entryFlow = new EntryFlow({
  onCreate({ url, root }) {
    return preview({ url, root, document: "" });
  },
  onOpen({ url, document }) {
    return preview({ url, document });
  },
  onExample() { loadExample("reponomics-dashboard"); },
  onCancel() {
    entryFlow.hide();
    fields.url.value = `${editor.owner}/${editor.repo}`;
    errorPanel.hidden = true;
    submit.focus({ preventScroll: true });
  },
});

function browseRepository(repo) {
  if (settingsPanel.matches(":popover-open")) settingsPanel.hidePopover();
  repoTooltip.hidden = true;
  entryFlow.browse(repo, { canReturn: Boolean(editor?.rows.length) });
  document.getElementById("replace-draft-warning").hidden = !userEdited;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  browseRepository(fields.url.value.trim());
});

document.querySelector(".wordmark").addEventListener("click", (event) => {
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  if (entryFlow.busy || (!editor?.rows.length && rowsList.getAttribute("aria-busy") === "true")) return;
  if (settingsPanel.matches(":popover-open")) settingsPanel.hidePopover();
  const repo = document.getElementById("entry").hidden ? fields.url.value : entryFlow.url;
  entryFlow.welcome(repo, Boolean(editor?.rows.length));
});

const resetDialog = document.getElementById("reset-dialog");
const resetConfirm = document.getElementById("reset-confirm");
document.getElementById("reset-tree").addEventListener("click", () => {
  resetDialog.querySelector(".dialog-error").hidden = true;
  const startingPoint = editor.document ? "Restore the document’s treestamp from the captured repository version." : "Restore this tree’s starting layout and formatting.";
  document.getElementById("reset-description").textContent = `${startingPoint} Your changes to notes, hidden entries, folds, and formatting will be removed.`;
  resetDialog.showModal();
  document.getElementById("reset-cancel").focus();
});
document.getElementById("reset-cancel").addEventListener("click", () => resetDialog.close());
resetDialog.addEventListener("cancel", (event) => {
  if (resetConfirm.disabled) event.preventDefault();
});

async function resetTree() {
  await waitForEdits();
  const revealed = reveal.checked;
  reveal.checked = false;
  const example = Object.entries(EXAMPLES).find(([, data]) =>
    data.state.generation === editor.state.generation);
  if (example) {
    loadExample(example[0]);
    return true;
  }
  const accepted = await preview({ owner: editor.owner, repo: editor.repo, ref: editor.ref, root: editor.root, document: editor.document });
  if (!accepted) reveal.checked = revealed;
  return accepted;
}

resetConfirm.addEventListener("click", async () => {
  resetConfirm.disabled = true;
  document.getElementById("reset-cancel").disabled = true;
  try {
    if (await resetTree()) resetDialog.close();
  } finally {
    resetConfirm.disabled = false;
    document.getElementById("reset-cancel").disabled = false;
  }
});

// Presentation changes apply to the current draft; entry choices stay provisional.
for (const name of ["style", "show_counts", "attribution"]) {
  fields[name].addEventListener("change", () => { if (editor) operate("present"); });
}
reveal.addEventListener("change", () => { if (editor) operate("restore"); });
showAll.addEventListener("click", () => { if (editor) operate("unhide_all"); });

function loadExample(name) {
  if (controller) controller.abort();
  controller = null;
  generation += 1;
  editingSession += 1;
  queue = Promise.resolve(true);
  reveal.checked = false;
  render(structuredClone(EXAMPLES[name]), true);
  entryFlow.hide(true);
  exampleContext.textContent = `Example: ${EXAMPLES[name].repository.owner}/${EXAMPLES[name].repository.name}`;
  exampleContext.hidden = false;
  setBusy(false, true);
}

async function copyText(text, fallbackNode) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_) {
    if (!fallbackNode) return false;
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(fallbackNode);
    selection.removeAllRanges();
    selection.addRange(range);
    try { return document.execCommand("copy"); } catch (_) { return false; }
  }
}

function setCopyStatus(label, explanation = "") {
  copyStatus.textContent = label;
  copyStatus.title = explanation;
}

copy.addEventListener("click", async () => {
  if (!editor) {
    setCopyStatus("Loading…", "Wait for the repository to finish opening.");
    return;
  }
  const session = editingSession;
  copy.disabled = true;
  setCopyStatus("Preparing…");
  try {
    const saved = await waitForEdits();
    if (!editor || session !== editingSession) {
      setCopyStatus("Repository changed", "Wait for the repository to open, then copy the block again.");
      return;
    }
    if (typeof editor.region !== "string") {
      setCopyStatus("No tree to copy");
      return;
    }
    const copied = await copyText(region.textContent, region);
    copyLabel.textContent = copied ? "Copied" : "Copy treestamp";
    copy.classList.toggle("copied", copied);
    const destination = !saved ? "Copied previous tree" : editor.document ? `Paste into ${displayPath(editor.document)}` : "Copied treestamp";
    setCopyStatus(copied ? destination : "Copy failed", copied ? "" : "Open Markdown and select the block to copy it manually.");
  } finally {
    copy.disabled = typeof editor?.region !== "string";
  }
});

function selectTab(name) {
  stage.dataset.view = name;
  for (const key of tabNames) {
    const active = key === name;
    tabs[key].setAttribute("aria-selected", active ? "true" : "false");
    tabs[key].tabIndex = active ? 0 : -1;
    panels[key].hidden = !active;
  }
}

// Wide layouts show settings in the sidebar; narrow layouts use a popover.
const wideLayout = matchMedia("(min-width: 48rem)");
wideLayout.addEventListener("change", (event) => {
  if (event.matches && settingsPanel.matches(":popover-open")) settingsPanel.hidePopover();
});

Object.entries(tabs).forEach(([name, tab]) => {
  tab.addEventListener("click", () => selectTab(name));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    const offset = event.key === "ArrowLeft" ? -1 : 1;
    let index = (tabNames.indexOf(name) + offset + tabNames.length) % tabNames.length;
    if (event.key === "Home") index = 0;
    if (event.key === "End") index = tabNames.length - 1;
    const next = tabNames[index];
    selectTab(next);
    tabs[next].focus();
  });
});

// Permalinks: /owner/repo or /owner/repo@sha, settings in the query, curation in the fragment.
(function boot() {
  const local = draftForLocation(window.location);
  if (local) {
    history.replaceState(null, "", local.address);
  }
  const route = parseRoute(window.location.pathname, window.location.hash);
  const query = new URLSearchParams(window.location.search);
  try { setValues(valuesFromQuery(query)); }
  catch (error) { showError(error.message, "", null); leaveStage(); return; }
  const address = window.location.pathname + window.location.search + window.location.hash;
  const example = Object.entries(EXAMPLES).find(([, data]) => addressFor(data.permalink, data.state, window.location.origin) === address);
  if (example) {
    loadExample(example[0]);
    return;
  }
  if (!route) {
    entryFlow.welcome();
    return;
  }
  const { owner, repo, sha, saved } = route;
  fields.url.value = `${owner}/${repo}`;
  document.getElementById("active-repository").textContent = `${owner}/${repo}`;
  if (window.location.hash.startsWith("#s=") && !saved) {
    entryFlow.hide();
    showError("This link contains invalid editing state.", "Open the repository to create a new tree.", null);
    return;
  }
  if (!query.has("document")) fields.document.value = DEFAULT_DOCUMENT;
  if (!sha && !saved && !window.location.search && !window.location.hash) {
    browseRepository(`${owner}/${repo}`);
    return;
  }
  // Captured sessions and explicit source settings open the editor directly.
  entryFlow.hide();
  const fresh = () => {
    const params = settingsParams();
    params.set("owner", owner);
    params.set("repo", repo);
    params.set("ref", sha || "HEAD");
    if (!query.has("document")) params.delete("document");
    return preview(params);
  };
  if (saved) {
    if (!sha || !saved.source || !saved.curation?.settings) {
      showError("This link does not contain a valid captured editing session.", "Open the repository to create a new tree.", null);
      return;
    }
    editor = { owner, repo, ref: sha, root: saved.source.root, document: saved.source.document, state: saved, rows: [], loaded: false };
    setValues(valuesFromSettings(saved.curation.settings));
    operate("restore");
    return;
  }
  fresh();
})();
