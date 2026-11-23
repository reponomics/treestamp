// Browse source paths without replacing the editor's current draft.
import { displayPath, pathKey } from "./logic.js";
import { treeGuides, appendTreeGuides } from "./tree-view.js";

const navigationKeys = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "Enter", " "]);

function isNavigationEvent(event) {
  return !event.altKey && !event.ctrlKey && !event.metaKey && !event.isComposing && navigationKeys.has(event.key);
}

export class SourceBrowser {
  constructor(container, { onSelect = () => {}, onError = () => {}, onBusy = () => {} } = {}) {
    this.container = container;
    this.container.tabIndex = -1;
    this.onSelect = onSelect;
    this.onError = onError;
    this.onBusy = onBusy;
    this.mode = "new";
    this.selected = { new: ".", document: "README.md", entry: "." };
    this.entries = new Map();
    this.children = new Map();
    this.expanded = new Set(["."]);
    this.focused = ".";
    this.disabled = false;
    this.controller = null;
    this.status = document.createElement("p");
    this.status.className = "source-browser-status group-note";
    this.status.setAttribute("role", "status");
    this.tree = document.createElement("ul");
    this.tree.className = "source-tree";
    this.tree.setAttribute("role", "tree");
    this.tree.addEventListener("keydown", (event) => this.keydown(event));
    container.replaceChildren(this.status, this.tree);
    this.setMode("new");
  }

  cancel() {
    this.controller?.abort();
    this.controller = null;
    this.tree.setAttribute("aria-busy", "false");
    this.onBusy(false);
  }

  reset() {
    this.cancel();
    this.entries.clear();
    this.children.clear();
    this.expanded = new Set(["."]);
    this.focused = ".";
    this.status.textContent = "";
    this.render();
  }

  async load(repo) {
    this.reset();
    const controller = new AbortController();
    this.controller = controller;
    this.status.textContent = "Loading repository…";
    this.tree.setAttribute("aria-busy", "true");
    this.onBusy(true);
    try {
      const response = await fetch(`/api/browse?${new URLSearchParams({ url: repo })}`, { signal: controller.signal });
      const data = await response.json();
      if (controller.signal.aborted || controller !== this.controller) return false;
      if (!response.ok) {
        const error = data.error || {};
        this.status.textContent = "Try loading the repository again.";
        this.onError(error.message || "Could not load the repository folders.", error.code, response.status);
        return false;
      }
      this.accept(data.entries);
      return true;
    } catch (error) {
      if (controller.signal.aborted || controller !== this.controller) return false;
      this.status.textContent = "Try loading the repository again.";
      this.onError("Could not load the repository folders. Check your connection and try again.", "network", 0);
      return false;
    } finally {
      if (controller === this.controller) {
        this.controller = null;
        this.tree.setAttribute("aria-busy", "false");
        this.onBusy(false);
      }
    }
  }

  accept(entries) {
    const waitingForTree = document.activeElement === this.container;
    this.entries = new Map(entries.map((entry) => [pathKey(entry.path), entry]));
    this.children.clear();
    for (const entry of entries) {
      if (entry.parent === null) continue;
      const parent = pathKey(entry.parent);
      if (!this.children.has(parent)) this.children.set(parent, []);
      this.children.get(parent).push(entry);
    }
    for (const children of this.children.values()) {
      children.sort((a, b) => Number(b.kind === "dir") - Number(a.kind === "dir") || displayPath(a.name).localeCompare(displayPath(b.name)));
    }
    this.status.textContent = "";
    this.select(this.selected[this.mode]);
    if (waitingForTree) this.focus();
  }

  setMode(mode) {
    this.mode = mode;
    const labels = { new: "Choose a tree root", document: "Choose a document", entry: "Repository entries" };
    this.tree.setAttribute("aria-label", labels[mode]);
    this.select(this.selected[mode]);
  }

  setDisabled(disabled) {
    const restoreFocus = this.container.contains(document.activeElement);
    this.disabled = disabled;
    this.tree.setAttribute("aria-disabled", String(disabled));
    this.render();
    if (!disabled && restoreFocus) this.focus();
  }

  selectable(entry) {
    if (this.mode === "entry") return entry.kind === "dir" || entry.kind === "file";
    return entry.kind === (this.mode === "new" ? "dir" : "file");
  }

  selectedEntry() {
    return this.entries.get(pathKey(this.selected[this.mode])) || null;
  }

  navigable(entry) {
    return entry.kind === "dir" || this.selectable(entry);
  }

  select(path, { notify = false } = {}) {
    this.selected[this.mode] = path;
    const entry = this.entries.get(pathKey(path));
    if (entry) {
      let parent = entry.parent;
      while (parent !== null && this.entries.has(pathKey(parent))) {
        this.expanded.add(pathKey(parent));
        parent = this.entries.get(pathKey(parent)).parent;
      }
      if (this.navigable(entry)) this.focused = pathKey(path);
    }
    this.render();
    if (notify && entry && this.selectable(entry)) this.onSelect(entry.path, this.mode, entry);
  }

  visibleEntries() {
    const visible = [];
    const visit = (entry, depth) => {
      visible.push({ entry, depth });
      if (!this.expanded.has(pathKey(entry.path))) return;
      for (const child of this.children.get(pathKey(entry.path)) || []) visit(child, depth + 1);
    };
    const root = this.entries.get(".");
    if (root) visit(root, 0);
    return visible;
  }

  focus() {
    const target = this.tree.querySelector('[tabindex="0"]') || this.container;
    target.focus({ preventScroll: true });
  }

  focusEntry(key) {
    this.focused = key;
    this.render();
    this.focus();
    this.tree.querySelector('[tabindex="0"]')?.scrollIntoView({ block: "nearest" });
  }

  toggle(entry) {
    const key = pathKey(entry.path);
    if (this.expanded.has(key)) this.expanded.delete(key);
    else this.expanded.add(key);
    this.focusEntry(key);
  }

  activate(entry) {
    if (this.disabled || !this.navigable(entry)) return;
    if (this.selectable(entry)) this.select(entry.path, { notify: true });
    else this.toggle(entry);
    this.focusEntry(pathKey(entry.path));
  }

  keydown(event) {
    if (this.disabled || !isNavigationEvent(event)) return;
    const target = event.target.closest('[role="treeitem"]');
    if (!target) return;
    const entry = this.entries.get(target.dataset.path);
    if (!entry) return;
    event.preventDefault();
    const visible = this.visibleEntries().map(({ entry }) => entry).filter((entry) => this.navigable(entry));
    const index = visible.findIndex((item) => pathKey(item.path) === pathKey(entry.path));
    if (["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      const positions = { ArrowUp: index - 1, ArrowDown: index + 1, Home: 0, End: visible.length - 1 };
      this.focusEntry(pathKey(visible[Math.max(0, Math.min(visible.length - 1, positions[event.key]))].path));
    } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      this.moveBranch(entry, event.key);
    } else this.activate(entry);
  }

  moveBranch(entry, key) {
    const identity = pathKey(entry.path);
    if (key === "ArrowLeft") {
      if (entry.kind === "dir" && this.expanded.has(identity)) this.toggle(entry);
      else if (entry.parent !== null) this.focusEntry(pathKey(entry.parent));
      return;
    }
    if (entry.kind !== "dir") return;
    if (!this.expanded.has(identity)) this.toggle(entry);
    else {
      const child = (this.children.get(identity) || []).find((item) => this.navigable(item));
      if (child) this.focusEntry(pathKey(child.path));
    }
  }

  row(entry, depth, guides) {
    const key = pathKey(entry.path);
    const item = document.createElement("li");
    item.className = "source-row";
    item.dataset.path = key;
    item.dataset.kind = entry.kind;
    item.setAttribute("role", "treeitem");
    item.setAttribute("aria-level", String(depth + 1));
    item.setAttribute("aria-selected", String(this.selectable(entry) && pathKey(this.selected[this.mode]) === key));
    item.setAttribute("aria-disabled", String(this.disabled || !this.navigable(entry)));
    item.tabIndex = !this.disabled && this.focused === key ? 0 : -1;
    item.addEventListener("focus", () => { this.focused = key; });
    item.addEventListener("click", () => this.activate(entry));
    appendTreeGuides(item, guides);
    const label = document.createElement("span");
    label.className = "source-name";
    label.textContent = entry.parent === null ? "./" : displayPath(entry.name) + (entry.kind === "dir" ? "/" : "");
    item.appendChild(label);
    this.appendToggle(item, entry);
    return item;
  }

  appendToggle(item, entry) {
    const key = pathKey(entry.path);
    if (entry.kind !== "dir" || !this.children.has(key)) return;
    const expanded = this.expanded.has(key);
    item.setAttribute("aria-expanded", String(expanded));
    const toggle = document.createElement("button");
    toggle.className = "source-toggle";
    toggle.textContent = expanded ? "▾" : "▸";
    toggle.type = "button";
    toggle.tabIndex = -1;
    toggle.disabled = this.disabled;
    const action = `${expanded ? "Collapse" : "Expand"} ${displayPath(entry.path)}`;
    toggle.setAttribute("aria-label", action);
    toggle.title = action;
    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!this.disabled) this.toggle(entry);
    });
    item.appendChild(toggle);
  }

  render() {
    const visible = this.visibleEntries();
    if (!visible.some(({ entry }) => pathKey(entry.path) === this.focused && this.navigable(entry))) this.focused = ".";
    const guides = treeGuides(visible);
    this.tree.replaceChildren(...visible.map(({ entry, depth }, index) => this.row(entry, depth, guides[index])));
    this.tree.hidden = visible.length === 0;
  }
}
