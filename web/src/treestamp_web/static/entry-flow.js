// Repository and source selection before adopting a new editing session.
import { hintFor } from "./logic.js";
import { SourceBrowser } from "./source-browser.js";

const element = (id) => document.getElementById(id);

// Keep repository context consistent for links, typed names, and restored sessions.
export function renderRepository(container, label) {
  container.title = label;
  const match = /^(?:https?:\/\/github\.com\/)?([^/\s]+)\/([^/\s]+)\/?$/.exec(label);
  if (!match) { container.textContent = label; return; }
  const parts = [match[1], "/", match[2]];
  const classes = ["repository-owner", "repository-separator", "repository-name"];
  container.replaceChildren(...parts.map((text, index) => {
    const span = document.createElement("span");
    span.className = classes[index];
    span.textContent = text;
    return span;
  }));
}

export class EntryFlow {
  constructor({ onCreate, onOpen, onExample, onCancel }) {
    this.onCreate = onCreate;
    this.onOpen = onOpen;
    this.onExample = onExample;
    this.onCancel = onCancel;
    this.url = "";
    this.canReturn = false;
    this.busy = false;
    this.loading = false;
    this.browser = new SourceBrowser(element("source-browser"), {
      onSelect: () => { this.clearError(); this.renderSelection(); },
      onError: (message, code, status) => this.showError(message, hintFor(code, status)),
      onBusy: (busy) => { this.loading = busy; this.renderSelection(); },
    });
    this.bindEvents();
  }

  bindEvents() {
    element("entry-url").addEventListener("input", () => {
      element("entry-browse").disabled = !element("entry-url").value.trim();
      this.clearError();
    });
    element("entry-form").addEventListener("submit", (event) => {
      event.preventDefault();
      if (!this.busy) this.browse(element("entry-url").value.trim(), { canReturn: this.canReturn });
    });
    element("entry-change-repo").addEventListener("click", () => this.welcome(this.url, this.canReturn));
    element("explore-example").addEventListener("click", () => this.onExample());
    for (const id of ["entry-return", "entry-return-welcome"]) {
      element(id).addEventListener("click", () => this.onCancel());
    }
    element("reload").addEventListener("click", () => this.submit());
  }

  showPanel(panel) {
    element("entry").hidden = false;
    element("workspace").hidden = true;
    element("entry-welcome").hidden = panel !== "welcome";
    element("reload-settings").hidden = panel !== "browse";
    document.body.classList.add("choosing-source");
    for (const id of ["entry-return", "entry-return-welcome"]) element(id).hidden = !this.canReturn;
  }

  welcome(repo = "", canReturn = false) {
    this.browser.cancel();
    this.canReturn = canReturn;
    this.url = repo;
    element("entry-url").value = repo;
    element("entry-browse").disabled = !repo.trim();
    this.clearError();
    this.showPanel("welcome");
    element("entry-url").focus({ preventScroll: true });
  }

  async browse(repo, { canReturn = false } = {}) {
    this.url = repo;
    this.canReturn = canReturn;
    this.clearError();
    renderRepository(element("load-target"), repo);
    this.browser.reset();
    this.browser.setMode("entry");
    this.browser.select(".");
    this.showPanel("browse");
    this.renderSelection();
    this.browser.focus();
    const loaded = await this.browser.load(repo);
    if (loaded) this.renderSelection();
    return loaded;
  }

  clearError() {
    for (const id of ["entry-error", "reload-error"]) element(id).hidden = true;
  }

  showError(message, hint = "") {
    for (const id of ["entry-error", "reload-error"]) {
      element(id).textContent = [message, hint].filter(Boolean).join(" ");
      element(id).hidden = false;
    }
  }

  setBusy(busy) {
    this.busy = busy;
    this.browser.setDisabled(busy);
    for (const id of ["entry-url", "entry-change-repo", "entry-return", "entry-return-welcome", "explore-example"]) element(id).disabled = busy;
    element("entry-browse").disabled = busy || !element("entry-url").value.trim();
    this.renderSelection();
  }

  renderSelection() {
    const selected = this.browser.selectedEntry();
    const directory = selected?.kind !== "file";
    element("reload").textContent = this.busy ? "Opening…" : directory ? "Create" : "Load";
    element("reload").disabled = this.busy || this.loading || !selected;
  }

  async submit() {
    const selected = this.browser.selectedEntry();
    if (this.busy || this.loading || !selected) return;
    this.clearError();
    this.setBusy(true);
    let accepted = false;
    try {
      accepted = selected.kind === "dir"
        ? await this.onCreate({ url: this.url, root: selected.path })
        : await this.onOpen({ url: this.url, document: selected.path });
      if (accepted) this.hide(true);
    } catch (_) {
      this.showError("Could not open this selection.", "Try again. Your current treestamp is unchanged.");
    } finally {
      this.setBusy(false);
      if (!accepted) this.restoreSelectionFocus();
    }
  }

  restoreSelectionFocus() {
    const active = document.activeElement;
    if (active === document.body || active === element("reload")) this.browser.focus();
  }

  hide(focusEditor = false) {
    this.browser.cancel();
    element("entry").hidden = true;
    element("workspace").hidden = false;
    document.body.classList.remove("choosing-source");
    if (focusEditor) {
      const row = element("rows").firstElementChild;
      row?.focus({ preventScroll: true });
      row?.scrollIntoView({ block: "nearest" });
    }
  }
}
