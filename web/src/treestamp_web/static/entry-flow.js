// Repository and source selection before adopting a new editing session.
import { entryErrorText, hintFor } from "./logic.js";
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
      this.renderWelcome();
      this.clearError();
    });
    element("entry-form").addEventListener("submit", (event) => {
      event.preventDefault();
      this.openRoot(event.submitter?.id === "entry-load" ? "file" : "dir");
    });
    element("entry-browse").addEventListener("click", () => {
      const repo = element("entry-url").value.trim();
      if (!this.busy && repo) this.browse(repo, { canReturn: this.canReturn });
    });
    element("entry-change-repo").addEventListener("click", () => this.welcome(this.url, this.canReturn));
    element("explore-example").addEventListener("click", () => this.onExample());
    element("entry-return-welcome").addEventListener("click", () => this.onCancel());
    element("source-create").addEventListener("click", () => this.submit("dir"));
    element("source-load").addEventListener("click", () => this.submit("file"));
  }

  showPanel(panel) {
    this.panel = panel;
    element("entry").hidden = false;
    element("workspace").hidden = true;
    element("entry-welcome").hidden = panel !== "welcome";
    element("reload-settings").hidden = panel !== "browse";
    document.body.classList.add("choosing-source");
    element("entry-return-welcome").hidden = !this.canReturn;
  }

  welcome(repo = "", canReturn = false) {
    this.browser.cancel();
    this.canReturn = canReturn;
    this.url = repo;
    element("entry-url").value = repo;
    this.renderWelcome();
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
    element("entry-url").removeAttribute("aria-invalid");
  }

  // The landing line replaces the field's label, so it is kept short; the picker has room for the hint.
  // Only an unusable address marks the field invalid; other failures leave it as typed.
  showError(message, hint = "", code = "") {
    element("entry-error").textContent = entryErrorText(code, message);
    element("reload-error").textContent = [message, hint].filter(Boolean).join(" ");
    for (const id of ["entry-error", "reload-error"]) element(id).hidden = false;
    if (code === "invalid_link") element("entry-url").setAttribute("aria-invalid", "true");
  }

  setBusy(busy) {
    this.busy = busy;
    this.browser.setDisabled(busy);
    for (const id of ["entry-url", "entry-change-repo", "entry-return-welcome", "explore-example"]) element(id).disabled = busy;
    this.renderWelcome();
    this.renderSelection();
  }

  renderWelcome() {
    const disabled = this.busy || !element("entry-url").value.trim();
    for (const id of ["entry-create", "entry-load", "entry-browse"]) element(id).disabled = disabled;
    element("entry-progress").textContent = this.busy ? this.opening || "Opening…" : "";
  }

  openRoot(kind) {
    const repo = element("entry-url").value.trim();
    if (this.busy || !repo) return;
    this.url = repo;
    return this.openSource(kind, kind === "dir" ? "." : "README.md");
  }

  renderSelection() {
    const selected = this.browser.selectedEntry();
    const unavailable = this.busy || this.loading;
    element("source-create").disabled = unavailable || selected?.kind !== "dir";
    element("source-load").disabled = unavailable || selected?.kind !== "file";
    element("source-progress").textContent = this.busy ? "Opening…" : "";
  }

  submit(kind) {
    const selected = this.browser.selectedEntry();
    if (this.busy || this.loading || selected?.kind !== kind) return;
    return this.openSource(kind, selected.path);
  }

  async openSource(kind, path) {
    this.clearError();
    this.opening = kind === "dir" ? "Creating treestamp…" : "Loading treestamp…";
    this.setBusy(true);
    let accepted = false;
    try {
      accepted = kind === "dir"
        ? await this.onCreate({ url: this.url, root: path })
        : await this.onOpen({ url: this.url, document: path });
      if (accepted) this.hide(true);
    } catch (_) {
      this.showError("Could not open this selection.", "Try again. Your current treestamp is unchanged.");
    } finally {
      this.setBusy(false);
      if (!accepted) {
        if (this.panel === "welcome") element("entry-url").focus({ preventScroll: true });
        else this.restoreSelectionFocus();
      }
    }
  }

  restoreSelectionFocus() {
    const active = document.activeElement;
    if (active === document.body || active === element("source-create") || active === element("source-load")) this.browser.focus({ reveal: true });
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
