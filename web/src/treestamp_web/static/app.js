// Preview and editor page. Talks to /api/preview and /api/op; renders text as text, never HTML.
// Decisions that need no DOM live in logic.js and are tested with node --test.

import { treeGuides, appendTreeGuides } from "./tree-view.js";
import { ExportView } from "./export-view.js";
import { EXAMPLES } from "./example.js";
import { EntryFlow, renderRepository } from "./entry-flow.js";
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

const fields = {
  url: document.getElementById("url"),
  style: document.getElementById("style"),
  root: document.getElementById("root"),
  show_counts: document.getElementById("show_counts"),
  attribution: document.getElementById("attribution"),
  document: document.getElementById("document"),
};
const visitRepo = document.getElementById("visit-repo");
const status = document.getElementById("status");
const errorPanel = document.getElementById("error");
const errorMessage = document.getElementById("error-message");
const errorHint = document.getElementById("error-hint");
document.getElementById("error-dismiss").addEventListener("click", (event) => {
  const restoreFocus = document.activeElement === event.currentTarget;
  errorPanel.hidden = true;
  if (restoreFocus) tabs[stage.dataset.view || "editor"].focus({ preventScroll: true });
});
const repoInfo = document.getElementById("repo-info");
const repoTooltip = document.getElementById("repo-tooltip");
const repoInfoDialog = document.getElementById("repo-info-dialog");
const settingsPanel = document.getElementById("settings");
const settingsTrigger = document.querySelector(".settings-open");
const tabs = { editor: document.getElementById("tab-editor"), stamp: document.getElementById("tab-stamp"), info: document.getElementById("tab-info") };
const panels = { editor: document.getElementById("editor-panel"), stamp: document.getElementById("stamp-panel"), info: document.getElementById("info-panel") };
const tabNames = Object.keys(tabs);
const stage = document.getElementById("result");
let generation = 0; // responses from an older request generation are ignored
const rowsList = document.getElementById("rows");
const treeToolbar = document.querySelector(".editor-toolbar");
const rowNote = document.getElementById("row-note");
const rowVisibility = document.getElementById("row-visibility");
const selectedPathLabel = document.getElementById("selected-path");
let selectedPath = "";
const reveal = document.getElementById("reveal");
const revealLabel = document.getElementById("reveal-label");
const showAll = document.getElementById("show-all");
const region = document.getElementById("region");
const copy = document.getElementById("copy");
const copyLabel = document.getElementById("copy-label");
const copyStatus = document.getElementById("copy-status");
const tuiMode = document.getElementById("tui-mode");
const keymapDialog = document.getElementById("keymap-dialog");
const noteDialog = document.getElementById("note-dialog");
const noteText = document.getElementById("note-text");
const noteSave = document.getElementById("note-save");
const noteCancel = document.getElementById("note-cancel");

const placement = new NotePlacement();
const exportView = new ExportView({
  getEditor: () => editor,
  waitForEdits,
  setAppearance: (appearance) => enqueueEdit(() => sendOperation("present", undefined, undefined, appearance)),
});

let controller = null;
let countdown = null;
// The editing session: identity of the commit plus the state the server hands back.
let editor = null;
// Presentation may temporarily show an incoming tree; only render() adopts it.
let presented = null;
let provisional = null;
let editingSession = 0;
let pendingDraft = draftForLocation(window.location);

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
    status.textContent = "Loading…";
  } else if (!countdown) {
    status.textContent = "";
  }
}

function clearCountdown() {
  if (countdown) {
    clearInterval(countdown);
    countdown = null;
    if (!status.classList.contains("busy")) {
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
    const tick = () => {
      status.textContent = `Retry in ${remaining}s`;
      if (remaining <= 0) {
        clearCountdown();
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
  const guides = treeGuides(rows);
  return rows.map((row, index) => rowElement(row, guides[index]));
}

function rowElement(row, guides) {
  const item = document.createElement("li");
  item.className = `row ${row.kind === "dir" ? "dir" : "leaf"}${row.hidden ? " hidden-row" : ""}`;
  item.dataset.path = row.path;
  const canFold = row.kind === "dir" && row.path !== "";
  // Focus selects the row for the shared toolbar; folder controls still fold it.
  item.tabIndex = row.path === "" ? 0 : -1;
  item.addEventListener("click", (event) => {
    if (event.target.closest("button, input")) return;
    item.focus({ preventScroll: true });
    if (canFold && window.getSelection().isCollapsed) operate("toggle", row.path);
  });
  appendTreeGuides(item, guides);

  item.appendChild(createRowName(row, canFold));
  appendRowDetails(item, row);
  return item;
}

function createRowName(row, canFold) {
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
  return name;
}

function appendRowDetails(item, row) {
  if (rowSuffix(row)) item.appendChild(Object.assign(document.createElement("span"), { className: "target", textContent: rowSuffix(row) }));
  if (row.kind === "dir" && row.collapsed && row.counts) item.appendChild(Object.assign(document.createElement("span"), { className: "counts", textContent: row.counts }));
  if (row.annotation) item.appendChild(Object.assign(document.createElement("span"), { className: "note", textContent: `# ${row.annotation}` }));
}

function selectRow(path) {
  const row = presented?.prepared.rows.find((entry) => entry.path === path);
  selectedPath = row?.path ?? "";
  for (const item of rowsList.children) {
    const selected = Boolean(row) && item.dataset.path === selectedPath;
    item.dataset.selected = String(selected);
    item.tabIndex = selected ? 0 : -1;
    if (selected) item.setAttribute("aria-current", "true");
    else item.removeAttribute("aria-current");
  }
  renderSelectionToolbar(row);
}

function renderSelectionToolbar(row) {
  const label = row ? (displayPath(row.identity) || ".") + (row.kind === "dir" ? "/" : "") : "No selection";
  selectedPathLabel.textContent = label;
  selectedPathLabel.title = label;
  rowNote.disabled = !row;
  rowVisibility.disabled = !row || row.path === "";
  rowVisibility.textContent = row?.hidden ? "Unhide" : "Hide";
  rowVisibility.title = row?.path === "" ? "The root is always included" : "";
}

rowsList.addEventListener("focusin", (event) => {
  const item = event.target.closest(".row");
  if (item) selectRow(item.dataset.path);
});

rowNote.addEventListener("click", () => {
  const path = selectedPath;
  enqueueEdit((saved) => {
    const row = editor.rows.find((entry) => entry.path === path);
    if (row && !document.querySelector("dialog[open]")) editAnnotation(row, "note");
    return saved;
  });
});
rowVisibility.addEventListener("click", () => {
  const path = selectedPath;
  enqueueEdit((saved) => {
    const row = editor.rows.find((entry) => entry.path === path);
    return row?.path ? toggleRowVisibility(row) : saved;
  });
});

let noteEditing = null;

function restoreTreeFocus(path, action) {
  const row = Array.from(rowsList.children).find((item) => item.dataset.path === path);
  const control = action === "note" ? rowNote : action && row?.querySelector(`button[data-action="${action}"]:not(:disabled)`);
  (control || row)?.focus({ preventScroll: true });
}

function editAnnotation(row, action) {
  noteEditing = { path: row.path, original: row.annotation || "", action, session: editingSession, saving: false, request: null, savedBefore: undefined };
  document.getElementById("note-name").textContent = row.path ? row.name : "./";
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
  const selectedIndex = Array.from(rowsList.children).findIndex((item) => item.dataset.path === selectedPath);
  rowsList.replaceChildren(...treeRowElements(rows));
  const selected = rows.find((row) => row.path === selectedPath) || rows[Math.max(0, Math.min(selectedIndex, rows.length - 1))];
  selectRow(selected?.path);
  if (focused === rowVisibility && rowVisibility.disabled) rowNote.focus({ preventScroll: true });
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
  showSettings(data, !opening && Boolean(previous?.rows.length));
  if (opening) selectedPath = "";
  presentPreview(data, prepared);
  pendingDraft = null;
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
    sourceFormat: data.source_format || "markdown",
    svgAppearance: data.svg_appearance || { style: "continuous", theme: "light" },
    sourceNotice: data.source_format === "svg"
      ? ((!opening && previous?.sourceNotice) || [data.notice || "Preview regenerated from embedded treestamp data. The exported SVG replaces the original drawing.", ...(data.warnings || [])].join(" ")) : "",
  };
  if (opening) {
    editingSession += 1;
    queue = Promise.resolve(true);
  }
  exportView.accept(editor, opening);
  history.replaceState(null, "", prepared.address);
  saveDraft(prepared.address);
}

// Render validated data without changing the accepted session, URL, or draft.
function presentPreview(data, prepared) {
  presented = { data, prepared };
  document.getElementById("tree-document").textContent = displayPath(data.document);
  document.querySelector(".canvas-caption").hidden = !data.document;
  status.textContent = "";

  document.querySelectorAll("[data-repo-branch]").forEach((node) => { node.textContent = data.repository.default_branch || "Unavailable"; });
  document.querySelectorAll("[data-repo-commit]").forEach((node) => { node.textContent = data.ref.commit; });
  visitRepo.href = data.repository.url;
  visitRepo.hidden = false;

  repoInfo.disabled = false;
  document.getElementById("reset-tree").disabled = false;
  renderRepository(document.getElementById("active-repository"), `${data.repository.owner}/${data.repository.name}`);
  fields.url.value = `${data.repository.owner}/${data.repository.name}`;

  renderRows(prepared.rows);
  document.getElementById("tree-attribution").hidden = !data.state.curation.settings.attribution;

  renderRegion(data.region);
  copy.disabled = false;
  copyLabel.textContent = "Copy Markdown";
  setCopyStatus("");
  copy.classList.remove("copied");
  const hiddenCount = data.state.curation.hidden.length;
  revealLabel.textContent = hiddenCount ? `Reveal hidden entries (${hiddenCount})` : "Reveal hidden entries";
  showAll.disabled = hiddenCount === 0;
  document.body.classList.remove("no-tree");
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

// ---------- requests

function rememberPreviewDOM() {
  // Keep the actual nodes so cancellation also preserves selection and controls
  // when there was no accepted tree yet (for example, a saved draft on startup).
  const containers = [rowsList, region, document.getElementById("active-repository")];
  const contents = containers.map((node) => [node, [...node.childNodes]]);
  const nodes = [
    document.getElementById("tree-document"), document.querySelector(".canvas-caption"),
    status, visitRepo, repoInfo, errorPanel,
    document.getElementById("reset-tree"), document.getElementById("tree-attribution"),
    copy, copyLabel, copyStatus, revealLabel, showAll, rowNote, rowVisibility, selectedPathLabel,
    ...document.querySelectorAll("[data-repo-branch], [data-repo-commit]"),
  ];
  const attributes = nodes.map((node) => [node, [...node.attributes].map(({ name, value }) => [name, value])]);
  // Only leaf labels have their text replaced; restoring a button's text would
  // discard its icon and other child elements.
  const labels = nodes.filter((node) => !node.children.length).map((node) => [node, node.textContent]);
  return () => {
    for (const [node, children] of contents) node.replaceChildren(...children);
    for (const [node, saved] of attributes) {
      for (const attribute of [...node.attributes]) node.removeAttribute(attribute.name);
      for (const [name, value] of saved) node.setAttribute(name, value);
    }
    for (const [node, text] of labels) node.textContent = text;
  };
}

function presentIncoming(body, prepared, ticket) {
  const entry = document.getElementById("entry");
  const workspace = document.getElementById("workspace");
  const restoreDOM = rememberPreviewDOM();
  const previous = {
    presented, selectedPath, values: formValues(), url: fields.url.value,
    view: stage.dataset.view, entryHidden: entry.hidden, workspaceHidden: workspace.hidden,
    choosing: document.body.classList.contains("choosing-source"),
    empty: document.body.classList.contains("no-tree"),
  };
  provisional = { ticket, restore() {
    presented = previous.presented;
    selectedPath = previous.selectedPath;
    restoreDOM();
    setValues(previous.values);
    fields.url.value = previous.url;
    selectTab(previous.view || "editor");
    entry.hidden = previous.entryHidden;
    workspace.hidden = previous.workspaceHidden;
    document.body.classList.toggle("choosing-source", previous.choosing);
    document.body.classList.toggle("no-tree", previous.empty);
  } };
  errorPanel.hidden = true;
  selectedPath = "";
  showSettings(body, false);
  presentPreview(body, prepared);
  selectTab("editor");
  entry.hidden = true;
  workspace.hidden = false;
  document.body.classList.remove("choosing-source");
  // The request has finished; only acceptance is pending while notes are reviewed.
  rowsList.setAttribute("aria-busy", "true");
  status.classList.remove("busy");
  status.textContent = "Review notes";
}

function restoreIncoming(ticket = provisional?.ticket) {
  if (!provisional || provisional.ticket !== ticket) return;
  const pending = provisional;
  provisional = null;
  pending.restore();
}

function finishIncoming(ticket, opening) {
  if (ticket === generation && rowsList.getAttribute("aria-busy") === "true") setBusy(false, opening);
  restoreIncoming(ticket);
}

async function acceptResponse(body, opening, ticket) {
  try {
    const prepared = preparePreview(body, window.location.origin);
    if (opening && body.placement?.total > 0) {
      // Validate the transfer tree before exposing either part of the preview.
      preparePreview({ ...body, rows: body.placement.rows }, window.location.origin);
      presentIncoming(body, prepared, ticket);
      const source = body;
      body = await placement.run(body);
      if (body) body = {
        ...body,
        notice: source.notice || body.notice,
        warnings: [...new Set([...(source.warnings || []), ...(body.warnings || [])])],
      };
    }
    if (!body || ticket !== generation) return false;
    setBusy(false, opening);
    render(body, opening);
    if (provisional?.ticket === ticket) provisional = null;
    return true;
  } catch (err) {
    if (ticket === generation) setBusy(false, opening);
    restoreIncoming(ticket);
    if (ticket !== generation) return false;
    showError("The page could not display the treestamp.", String(err && err.message), null);
    return false;
  } finally {
    finishIncoming(ticket, opening);
  }
}

function rejectResponse(body, responseStatus) {
  const error = (body && body.error) || {};
  const message = error.message || `The service returned status ${responseStatus}.`;
  const hint = error.code === "snapshot_unavailable" && !editor?.rows.length
    ? document.getElementById("entry").hidden
      ? "Choose the treestamp wordmark to return to the start page."
      : "Browse the repository to start a new treestamp."
    : hintFor(error.code, responseStatus);
  showError(message, hint, error.retry_after || null);
  return false;
}

// Previews cancel earlier previews. Edits run sequentially so each request
// uses the preceding accepted state.
async function call(url, init, { abortable }) {
  restoreIncoming();
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
    showError("Could not reach the service.", "Check your connection and try again.", null);
    return false;
  }
  if (mine.signal.aborted || ticket !== generation) return false;
  setBusy(false, abortable);
  if (response.ok && body) return acceptResponse(body, abortable, ticket);
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
  exportView.invalidate();
  const session = editingSession;
  queue = queue.then((saved) => {
    if (!editor || session !== editingSession) return false;
    return action(saved);
  });
  queue.then(() => exportView.showOutput());
  return queue;
}

async function sendOperation(type, path, text, appearance) {
  const accepted = editor;
  const body = opBody(editor, settingsFromForm(editor.state.curation.settings), reveal.checked, type, path, text);
  if (appearance) body.state.svg_appearance = appearance;
  const saved = await call("/api/op", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, { abortable: false });
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
  renderRepository(document.getElementById("repo-info-name"), fields.url.value);
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
  const toolbar = treeToolbar.getBoundingClientRect();
  const visibleHeight = Math.min(pane.bottom, window.innerHeight) - Math.max(pane.top, toolbar.bottom, 0);
  const pageSize = Math.max(1, Math.floor(visibleHeight / item.getBoundingClientRect().height) - 1);
  const next = treeNavigation(editor.rows, editor.state.curation.expanded.map(pathKey), index, key, pageSize);
  if (next.operation) return sendOperation(next.operation, item.dataset.path);
  const target = rowsList.children[next.index];
  target.focus({ preventScroll: true });
  rowsList.style.setProperty("--selection-toolbar-height", `${toolbar.height}px`);
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
  return sendOperation(row.hidden ? "unhide" : "hide", row.path);
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
  onExample() { loadExample("treestamp"); },
  onCancel: resumeSession,
});

function browseRepository(repo) {
  if (settingsPanel.matches(":popover-open")) settingsPanel.hidePopover();
  repoTooltip.hidden = true;
  entryFlow.browse(repo, { canReturn: Boolean(editor?.rows.length || pendingDraft) });
}

function openWelcome() {
  if (entryFlow.busy) return;
  if (settingsPanel.matches(":popover-open")) settingsPanel.hidePopover();
  repoTooltip.hidden = true;
  const repo = document.getElementById("entry").hidden ? fields.url.value : entryFlow.url;
  entryFlow.welcome(repo, Boolean(editor?.rows.length || pendingDraft));
}

async function resumeSession() {
  if (editor?.rows.length) {
    entryFlow.hide();
    fields.url.value = `${editor.owner}/${editor.repo}`;
    errorPanel.hidden = true;
    tabs[stage.dataset.view || "editor"].focus({ preventScroll: true });
    return;
  }
  if (!pendingDraft || entryFlow.busy) return;
  const address = new URL(pendingDraft.address, window.location.origin);
  const example = exampleAt(pendingDraft.address);
  if (example) { loadExample(example[0]); return; }
  const { owner, repo, sha, saved } = parseRoute(address.pathname, address.hash);
  editor = { owner, repo, ref: sha, root: saved.source.root, document: saved.source.document, state: saved, rows: [], loaded: false };
  fields.url.value = `${owner}/${repo}`;
  setValues(valuesFromSettings(saved.curation.settings));
  entryFlow.clearError();
  entryFlow.setBusy(true);
  try {
    if (await operate("restore")) entryFlow.hide(true);
  } finally {
    entryFlow.setBusy(false);
  }
}

document.querySelector(".wordmark").addEventListener("click", (event) => {
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  if (entryFlow.busy || (!editor?.rows.length && rowsList.getAttribute("aria-busy") === "true")) return;
  openWelcome();
});

const resetDialog = document.getElementById("reset-dialog");
const resetConfirm = document.getElementById("reset-confirm");
document.getElementById("reset-tree").addEventListener("click", () => {
  resetDialog.querySelector(".dialog-error").hidden = true;
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
  const accepted = await operate("reset");
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
  restoreIncoming();
  placement.cancel();
  if (controller) controller.abort();
  controller = null;
  generation += 1;
  editingSession += 1;
  queue = Promise.resolve(true);
  reveal.checked = false;
  render(structuredClone(EXAMPLES[name]), true);
  entryFlow.hide(true);
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
      setCopyStatus("No treestamp to copy");
      return;
    }
    const copied = await copyText(region.textContent, region);
    copyLabel.textContent = copied ? "Copied" : "Copy Markdown";
    copy.classList.toggle("copied", copied);
    const destination = !saved ? "Copied previous treestamp" : editor.document && editor.sourceFormat !== "svg" ? `Paste into ${displayPath(editor.document)}` : "Copied treestamp";
    setCopyStatus(copied ? destination : "Copy failed", copied ? "" : "Open Export, choose Markdown, and select the block to copy it manually.");
  } finally {
    copy.disabled = typeof editor?.region !== "string";
  }
});

function selectTab(name) {
  const editing = name === "editor";
  if (!editing && settingsPanel.matches(":popover-open")) settingsPanel.hidePopover();
  settingsPanel.hidden = !editing;
  settingsTrigger.hidden = !editing;
  stage.dataset.view = name;
  exportView.setVisible(name === "stamp");
  for (const key of tabNames) {
    const active = key === name;
    tabs[key].setAttribute("aria-selected", active ? "true" : "false");
    tabs[key].tabIndex = active ? 0 : -1;
    panels[key].hidden = !active;
  }
}

// Wide layouts show settings in the sidebar; narrow layouts use a popover.
const wideLayout = matchMedia("(min-width: 64rem)");
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
function exampleAt(address) {
  return Object.entries(EXAMPLES).find(([, data]) => addressFor(data.permalink, data.state, window.location.origin) === address);
}

(function boot() {
  if (pendingDraft) {
    const address = new URL(pendingDraft.address, window.location.origin);
    const { owner, repo } = parseRoute(address.pathname, address.hash);
    fields.url.value = `${owner}/${repo}`;
    if (window.location.pathname === "/") entryFlow.welcome(fields.url.value, true);
    else browseRepository(fields.url.value);
    return;
  }
  const route = parseRoute(window.location.pathname, window.location.hash);
  const query = new URLSearchParams(window.location.search);
  try { setValues(valuesFromQuery(query)); }
  catch (error) { showError(error.message, "", null); return; }
  const address = window.location.pathname + window.location.search + window.location.hash;
  const example = exampleAt(address);
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
  renderRepository(document.getElementById("active-repository"), `${owner}/${repo}`);
  if (window.location.hash.startsWith("#s=") && !saved) {
    entryFlow.hide();
    showError("This link contains invalid editing state.", "Open the repository to create a new treestamp.", null);
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
      showError("This link does not contain a valid captured editing session.", "Open the repository to create a new treestamp.", null);
      return;
    }
    editor = { owner, repo, ref: sha, root: saved.source.root, document: saved.source.document, state: saved, rows: [], loaded: false };
    setValues(valuesFromSettings(saved.curation.settings));
    operate("restore");
    return;
  }
  fresh();
})();
