// A provisional, one-time load step. Intermediate responses never enter the editor
// or local storage; the shared Python placement model owns all transfer decisions.
import { displayPath, pathKey, preparePreview, rowName, treeNavigation, hintFor } from "./logic.js";

const element = (id) => document.getElementById(id);
const moveKeys = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown", " "]);

function isModifiedKey(event) {
  return event.altKey || event.ctrlKey || event.metaKey || event.isComposing;
}

function browserRows(data) {
  const rows = data.placement?.rows;
  if (!Array.isArray(rows) || !rows.length) throw new Error("The destination tree is unavailable.");
  // Validate rows using the same contract as the ordinary editor.
  return preparePreview({ ...data, rows }, window.location.origin).rows;
}

function requestBody(initial, decisions, expanded, reveal) {
  return {
    owner: initial.repository.owner, repo: initial.repository.name,
    ref: initial.ref.commit, root: initial.root, document: initial.document,
    state: initial.state, decisions, expanded, reveal,
  };
}

export class NotePlacement {
  constructor() {
    this.dialog = element("placement-dialog");
    this.replaceDialog = element("placement-replace-dialog");
    this.tree = element("placement-rows");
    this.busy = false;
    this.resolve = null;
    this.bind();
  }

  bind() {
    element("placement-start").addEventListener("click", () => this.start());
    element("placement-decline").addEventListener("click", () => this.finish());
    element("placement-finish").addEventListener("click", () => this.finish());
    element("placement-place").addEventListener("click", () => this.place());
    element("placement-skip").addEventListener("click", () => this.skip());
    element("placement-undo").addEventListener("click", () => this.undo());
    element("placement-folder").addEventListener("click", () => this.fold());
    element("placement-reveal").addEventListener("change", (event) => this.request(this.decisions, this.expanded, event.target.checked));
    element("placement-replace-cancel").addEventListener("click", () => this.replaceDialog.close());
    element("placement-replace-accept").addEventListener("click", () => {
      this.replaceDialog.close();
      this.request([...this.decisions, { ...this.conflictDecision, replace: true }]);
    });
    this.replaceDialog.addEventListener("close", () => this.focus());
    this.dialog.addEventListener("cancel", (event) => { event.preventDefault(); this.finish(); });
    this.tree.addEventListener("keydown", (event) => this.keydown(event));
  }

  run(initial) {
    this.cancel();
    this.initial = initial;
    this.accepted = initial;
    this.rows = browserRows(initial);
    this.decisions = [];
    this.expanded = [...initial.state.curation.expanded];
    this.reveal = false;
    this.selected = this.rows[0].path;
    this.active = false;
    this.busy = false;
    this.dialog.classList.remove("placing");
    element("placement-choice").hidden = false;
    element("placement-work").hidden = true;
    element("placement-error").hidden = true;
    const count = initial.placement.total;
    element("placement-choice-title").textContent = `${count} ${count === 1 ? "note lost its place" : "notes lost their place"}.`;
    element("placement-reveal").checked = false;
    this.dialog.showModal();
    element("placement-start").focus();
    return new Promise((resolve) => { this.resolve = resolve; });
  }

  cancel() {
    this.controller?.abort();
    this.controller = null;
    this.settle(null);
  }

  settle(result) {
    if (this.replaceDialog.open) this.replaceDialog.close();
    if (this.dialog.open) this.dialog.close();
    const resolve = this.resolve;
    this.resolve = null;
    resolve?.(result);
  }

  finish() {
    if (this.busy || !this.resolve) return;
    this.settle(this.accepted);
  }

  start() {
    this.active = true;
    element("placement-choice").hidden = true;
    element("placement-work").hidden = false;
    this.dialog.classList.add("placing");
    this.render();
    this.setBusy(false);
    this.focus();
  }

  currentRow() {
    return this.rows.find((row) => row.path === this.selected) || this.rows[0];
  }

  focus() {
    if (!this.dialog.open || !this.active) return;
    const row = [...this.tree.children].find((item) => item.dataset.path === this.selected);
    row?.focus({ preventScroll: true });
    row?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  select(path, focus = true) {
    if (this.busy) return;
    this.selected = path;
    for (const item of this.tree.children) {
      const selected = item.dataset.path === path;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
    }
    this.renderTarget();
    if (focus) this.focus();
  }

  renderTarget() {
    const row = this.currentRow();
    const current = this.accepted.placement.current;
    element("placement-target").textContent = displayPath(row.identity) || "./";
    const compatible = (current.kind === "dir") === (row.kind === "dir");
    element("placement-place").disabled = this.busy || !compatible;
    const folder = element("placement-folder");
    folder.hidden = row.kind !== "dir" || row.path === "";
    folder.textContent = row.collapsed ? "Open folder" : "Close folder";
    folder.disabled = this.busy;
    element("placement-target-hint").textContent = compatible
      ? (row.hidden ? "Placing here will include this hidden entry." : "")
      : current.kind === "dir" ? "Choose a folder for this directory." : "Choose a file, or open this folder to look inside.";
  }

  rowElement(row) {
    const item = document.createElement("li");
    item.className = "placement-row";
    item.dataset.path = row.path;
    item.dataset.kind = row.kind;
    item.setAttribute("role", "treeitem");
    item.setAttribute("aria-level", String(row.depth + 1));
    item.setAttribute("aria-label", `${displayPath(row.identity) || "Repository root"}${row.hidden ? " (hidden)" : ""}`);
    if (row.kind === "dir") item.setAttribute("aria-expanded", String(!row.collapsed));
    item.style.setProperty("--placement-depth", row.depth);
    item.addEventListener("click", () => this.select(row.path));
    item.addEventListener("focus", () => { if (!this.busy) this.select(row.path, false); });
    item.addEventListener("dblclick", () => { if (row.kind === "dir") this.fold(); });
    const name = document.createElement("span");
    name.className = "placement-name";
    name.textContent = rowName(row);
    item.appendChild(name);
    if (row.collapsed && row.counts) {
      const counts = document.createElement("span");
      counts.className = "placement-counts";
      counts.textContent = row.counts;
      item.appendChild(counts);
    }
    if (row.annotation) {
      const note = document.createElement("span");
      note.className = "placement-row-note";
      note.textContent = `# ${row.annotation}`;
      item.appendChild(note);
    }
    if (row.hidden) item.classList.add("hidden-row");
    return item;
  }

  render() {
    const info = this.accepted.placement;
    const current = info.current;
    element("placement-progress").textContent = `${info.remaining} left · ${info.placed_count} placed`;
    element("placement-source").textContent = displayPath(current.path) + (current.kind === "dir" ? "/" : "");
    element("placement-note").textContent = current.annotation || "Place this folder to carry the notes inside it.";
    element("placement-directory-hint").hidden = current.kind !== "dir";
    const scrollTop = this.tree.scrollTop;
    this.tree.replaceChildren(...this.rows.map((row) => this.rowElement(row)));
    if (!this.rows.some((row) => row.path === this.selected)) this.selected = this.rows[0].path;
    this.select(this.selected, false);
    this.tree.scrollTop = scrollTop;
    element("placement-undo").disabled = this.busy || !this.decisions.length;
    element("placement-reveal").checked = this.reveal;
  }

  setBusy(value) {
    this.busy = value;
    this.tree.setAttribute("aria-busy", String(value));
    for (const id of ["placement-skip", "placement-finish", "placement-reveal"]) element(id).disabled = value;
    element("placement-undo").disabled = value || !this.decisions.length;
    this.renderTarget();
  }

  async request(decisions, expanded = this.expanded, reveal = this.reveal) {
    if (this.busy || !this.resolve) return;
    this.setBusy(true);
    element("placement-error").hidden = true;
    const controller = new AbortController();
    this.controller = controller;
    try {
      const response = await fetch("/api/placement", {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
        body: JSON.stringify(requestBody(this.initial, decisions, expanded, reveal)),
      });
      const body = await response.json();
      if (controller.signal.aborted || !this.resolve) return;
      if (!response.ok) { this.reject(body, response.status, decisions); return; }
      preparePreview(body, window.location.origin);
      this.rows = browserRows(body);
      this.accepted = body;
      this.decisions = decisions;
      this.expanded = expanded;
      this.reveal = reveal;
      if (!body.placement.current) this.settle(body);
    } catch (error) {
      if (!controller.signal.aborted) this.error("Could not update placement. Your last decision is unchanged. Try again.");
    } finally {
      this.finishRequest(controller);
    }
  }

  finishRequest(controller) {
    if (this.controller !== controller) return;
    this.controller = null;
    this.busy = false;
    if (!this.resolve) return;
    this.render();
    this.setBusy(false);
    if (!this.replaceDialog.open) this.focus();
  }

  reject(body, status, decisions) {
    const error = body?.error || {};
    if (status === 409 && error.code === "placement_conflict") {
      this.conflictDecision = decisions[decisions.length - 1];
      element("placement-replace-question").textContent = error.question || error.message;
      this.replaceDialog.showModal();
      element("placement-replace-cancel").focus();
      return;
    }
    this.error([error.message || "Could not update placement.", hintFor(error.code, status)].filter(Boolean).join(" "));
  }

  error(message) {
    element("placement-error").textContent = message;
    element("placement-error").hidden = false;
  }

  place() {
    const row = this.currentRow();
    const source = this.accepted.placement.current;
    if (!source || (source.kind === "dir") !== (row.kind === "dir")) return;
    this.request([...this.decisions, { type: "place", path: row.identity }]);
  }

  skip() { this.request([...this.decisions, { type: "skip" }]); }
  undo() { if (this.decisions.length) this.request(this.decisions.slice(0, -1)); }

  fold(operation = "toggle") {
    const row = this.currentRow();
    if (row.kind !== "dir" || row.path === "") return;
    const expanded = this.expanded.filter((path) => pathKey(path) !== row.path);
    if (operation === "expand" || (operation === "toggle" && row.collapsed)) expanded.push(row.identity);
    this.request(this.decisions, expanded);
  }

  keydown(event) {
    if (isModifiedKey(event) || this.busy) return;
    if (!event.target.closest('[role="treeitem"]')) return;
    if (event.key === "Enter" || event.key === "s" || event.key === "u") {
      event.preventDefault();
      ({ Enter: () => this.place(), s: () => this.skip(), u: () => this.undo() })[event.key]();
    } else if (moveKeys.has(event.key)) {
      event.preventDefault();
      const index = Math.max(0, this.rows.findIndex((row) => row.path === this.selected));
      const page = Math.max(1, Math.floor(this.tree.clientHeight / 36) - 1);
      const next = treeNavigation(this.rows, this.expanded.map(pathKey), index, event.key, page);
      if (next.operation) this.fold(next.operation);
      else this.select(this.rows[next.index].path);
    }
  }
}
