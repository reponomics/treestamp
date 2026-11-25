// Export keeps complete renderer-produced variants; the browser never edits SVG.
import { displayPath } from "./logic.js";

const THEMES = ["auto", "light", "dark"];
const PREPARE_TIMEOUT = 30_000;

function abortable(promise, signal) {
  return new Promise((resolve, reject) => {
    const settle = (finish, value) => {
      signal.removeEventListener("abort", aborted);
      finish(value);
    };
    const aborted = () => settle(reject, signal.reason);
    signal.addEventListener("abort", aborted, { once: true });
    promise.then(value => settle(resolve, value), error => settle(reject, error));
    if (signal.aborted) aborted();
  });
}

function wait(milliseconds, signal) {
  let timer;
  return abortable(new Promise(resolve => { timer = setTimeout(resolve, milliseconds); }), signal)
    .finally(() => clearTimeout(timer));
}

function retryDelay(response) {
  const value = response.headers.get("Retry-After");
  const seconds = value === null ? NaN : Number(value);
  const date = Date.parse(value || "");
  const delay = Number.isFinite(seconds) ? seconds * 1000 : date - Date.now();
  return Math.max(1000, Number.isFinite(delay) ? delay : 1000) + Math.random() * 250;
}

async function requestBundle(body, signal, waiting) {
  while (!signal.aborted) {
    const response = await fetch("/api/export/svg", {
      method: "POST", headers: { "Content-Type": "application/json" }, body, signal,
    });
    const result = await response.json();
    if (response.ok) return result.variants;
    if (response.status !== 429 && !(response.status === 503 && result.error?.code === "svg_busy")) {
      throw new Error(result.error?.message || "SVG could not be generated.");
    }
    waiting();
    await wait(retryDelay(response), signal);
  }
  throw signal.reason;
}

function releaseBundle(bundle) {
  for (const resource of Object.values(bundle || {})) URL.revokeObjectURL(resource.url);
}

async function decodeBundle(variants, signal) {
  if (!variants || THEMES.some(theme => typeof variants[theme] !== "string")) {
    throw new Error("SVG could not be generated.");
  }
  const blobs = THEMES.map(theme => {
    const blob = new Blob([variants[theme]], { type: "image/svg+xml" });
    if (blob.size > 1024 * 1024) throw new Error("SVG exceeds the file size limit.");
    return blob;
  });
  const bundle = {};
  try {
    const decoding = THEMES.map(async (theme, index) => {
      const svg = variants[theme];
      const blob = blobs[index];
      const url = URL.createObjectURL(blob);
      const image = new Image();
      bundle[theme] = { svg, url, image };
      image.src = url;
      await image.decode();
    });
    await abortable(Promise.all(decoding), signal);
    return bundle;
  } catch (error) {
    releaseBundle(bundle);
    throw error;
  }
}

export class ExportView {
  constructor({ getEditor, waitForEdits }) {
    this.getEditor = getEditor;
    this.waitForEdits = waitForEdits;
    this.output = document.getElementById("output-format");
    this.theme = document.getElementById("svg-theme");
    this.image = document.getElementById("svg-image");
    this.preview = document.getElementById("svg-preview");
    this.status = document.getElementById("svg-status");
    this.copy = document.getElementById("svg-copy");
    this.download = document.getElementById("svg-download");
    this.retry = document.getElementById("svg-retry");
    this.size = document.getElementById("svg-size");
    this.visible = false;
    this.bundle = null;
    this.operation = null;
    this.output.addEventListener("change", () => {
      this.invalidate();
      this.showOutput();
      if (this.output.value === "svg" && this.visible) this.prepare();
    });
    this.theme.addEventListener("change", () => this.display());
    this.retry.addEventListener("click", () => this.prepare());
    this.copy.addEventListener("click", () => this.deliver("copy"));
    this.download.addEventListener("click", () => this.deliver("download"));
    this.size.addEventListener("click", () => this.setActualSize(this.size.getAttribute("aria-pressed") !== "true"));
  }

  accept(editor, opening) {
    if (opening || this.source !== editor.state.generation) {
      this.source = editor.state.generation;
      this.initialAppearance = editor.sourceFormat === "svg" ? editor.svgAppearance : { style: "continuous", theme: "auto" };
      this.reset();
    } else if (!this.operation?.waitingForEdits) {
      this.invalidate();
    }
    const notice = document.getElementById("svg-source-notice");
    notice.textContent = editor.sourceNotice || "";
    notice.hidden = !editor.sourceNotice;
    this.showOutput();
  }

  setVisible(visible) {
    this.visible = visible;
    if (!visible) this.reset();
    this.showOutput();
  }

  reset() {
    this.invalidate();
    this.output.value = "markdown";
    this.theme.value = this.initialAppearance?.theme || "auto";
    this.preview.dataset.theme = this.theme.value;
    this.setActualSize(false);
  }

  setActualSize(actual) {
    this.size.setAttribute("aria-pressed", String(actual));
    this.size.textContent = actual ? "Fit width" : "Actual size";
    this.preview.dataset.actualSize = String(actual);
  }

  showOutput() {
    const svg = this.output.value === "svg";
    document.getElementById("result").dataset.output = this.output.value;
    document.getElementById("markdown-controls").hidden = svg;
    document.getElementById("region").hidden = svg;
    document.getElementById("svg-output").hidden = !svg;
  }

  invalidate() {
    if (this.operation) {
      clearTimeout(this.operation.timer);
      this.operation.controller.abort();
      this.operation = null;
    }
    releaseBundle(this.bundle);
    this.bundle = null;
    this.image.hidden = true;
    this.image.removeAttribute("src");
    this.copy.disabled = true;
    this.download.disabled = true;
    this.copy.textContent = "Copy SVG";
    this.retry.hidden = true;
    this.size.hidden = true;
    this.preview.setAttribute("aria-busy", "false");
    this.message("");
  }

  message(text, error = false) {
    this.status.textContent = text;
    this.status.dataset.error = String(error);
  }

  startOperation() {
    this.invalidate();
    const operation = { controller: new AbortController(), waitingForEdits: true };
    operation.timer = setTimeout(() => {
      operation.controller.abort(new Error("SVG couldn’t be prepared right now. Try again."));
    }, PREPARE_TIMEOUT);
    this.operation = operation;
    this.preview.setAttribute("aria-busy", "true");
    this.message("Preparing SVG…");
    return operation;
  }

  async acceptedInput(operation) {
    const saved = await abortable(this.waitForEdits(), operation.controller.signal);
    operation.waitingForEdits = false;
    if (!saved) throw new Error("An edit could not be applied. Resolve it before exporting SVG.");
    const editor = this.getEditor();
    if (!editor?.region || this.operation !== operation) return null;
    const settings = editor.state.curation.settings;
    const body = JSON.stringify({ region: editor.region, text_style: settings.style, show_counts: settings.show_counts, style: this.initialAppearance?.style || "continuous" });
    return { editor, body };
  }

  async prepare() {
    if (!this.visible || this.output.value !== "svg" || this.operation) return;
    const operation = this.startOperation();
    const signal = operation.controller.signal;
    try {
      const input = await this.acceptedInput(operation);
      if (!input) return;
      const { editor, body } = input;
      const variants = await requestBundle(body, signal, () => this.message("SVG generation is busy. Waiting to try again…"));
      const bundle = await decodeBundle(variants, signal);
      if (this.operation !== operation || editor !== this.getEditor()) {
        releaseBundle(bundle);
        return;
      }
      this.bundle = bundle;
      this.display();
    } catch (error) {
      this.preparationFailed(operation, error);
    } finally {
      clearTimeout(operation.timer);
      if (this.operation === operation) {
        this.operation = null;
        this.preview.setAttribute("aria-busy", "false");
      }
    }
  }

  preparationFailed(operation, error) {
    if (this.operation !== operation) return;
    this.message(error.message || "SVG could not be generated. Try again.", true);
    this.retry.hidden = false;
  }

  display() {
    this.preview.dataset.theme = this.theme.value;
    const resource = this.bundle?.[this.theme.value];
    if (!resource) return;
    this.image.src = resource.url;
    this.image.hidden = false;
    this.size.hidden = false;
    this.copy.disabled = false;
    this.download.disabled = false;
    this.copy.textContent = "Copy SVG";
    this.message("");
  }

  currentResource() {
    return this.bundle?.[this.theme.value];
  }

  isCurrent(resource, editor) {
    return editor === this.getEditor() && resource === this.currentResource();
  }

  async copyResource(resource, editor) {
    await navigator.clipboard.writeText(resource.svg);
    if (!this.isCurrent(resource, editor)) return;
    this.copy.textContent = "Copied";
    this.message("SVG source copied.");
  }

  downloadResource(resource, editor) {
    const link = document.createElement("a");
    link.href = resource.url;
    link.download = editor.sourceFormat === "svg" ? displayPath(editor.document).split("/").pop() : "treestamp.svg";
    link.click();
    this.message("SVG download started.");
  }

  async deliver(action) {
    const editor = this.getEditor();
    const resource = this.currentResource();
    if (!resource) return;
    this.copy.disabled = true;
    this.download.disabled = true;
    try {
      const saved = await this.waitForEdits();
      if (!saved || !this.isCurrent(resource, editor)) return;
      if (action === "copy") await this.copyResource(resource, editor);
      else this.downloadResource(resource, editor);
    } catch (_) {
      if (!this.isCurrent(resource, editor)) return;
      this.message(action === "copy" ? "Copy failed. Download the SVG instead." : "Download failed. Try again or copy the SVG.", true);
    } finally {
      this.copy.disabled = !this.bundle;
      this.download.disabled = !this.bundle;
    }
  }
}
