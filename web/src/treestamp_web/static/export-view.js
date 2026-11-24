// SVG is an export representation of the accepted document. It never changes
// the source path or inserts uploaded markup into the page.
import { displayPath } from "./logic.js";

export class ExportView {
  constructor({ getEditor, waitForEdits, setAppearance }) {
    this.getEditor = getEditor;
    this.waitForEdits = waitForEdits;
    this.setAppearance = setAppearance;
    this.output = document.getElementById("output-format");
    this.theme = document.getElementById("svg-theme");
    this.image = document.getElementById("svg-image");
    this.preview = document.getElementById("svg-preview");
    this.status = document.getElementById("svg-status");
    this.copy = document.getElementById("svg-copy");
    this.download = document.getElementById("svg-download");
    this.size = document.getElementById("svg-size");
    this.appearance = { style: "continuous", theme: "light" };
    this.visible = false;
    this.serial = 0;
    this.resource = null;
    this.request = null;
    this.output.addEventListener("change", () => this.showOutput());
    this.theme.addEventListener("change", () => this.changeAppearance());
    this.copy.addEventListener("click", () => this.deliver("copy"));
    this.download.addEventListener("click", () => this.deliver("download"));
    this.size.addEventListener("click", () => {
      const actual = this.size.getAttribute("aria-pressed") !== "true";
      this.size.setAttribute("aria-pressed", String(actual));
      this.size.textContent = actual ? "Fit width" : "Actual size";
      this.preview.dataset.actualSize = String(actual);
    });
  }

  accept(editor, opening) {
    if (opening || !this.source) {
      this.source = editor.state.generation;
      this.output.value = editor.sourceFormat;
      this.appearance = editor.sourceFormat === "svg" ? editor.svgAppearance : {
        style: "continuous", theme: document.documentElement.dataset.theme === "dark" ? "dark" : "light",
      };
    } else if (editor.sourceFormat === "svg") {
      this.appearance = editor.svgAppearance;
    }
    this.theme.value = this.appearance.theme;
    const notice = document.getElementById("svg-source-notice");
    notice.textContent = editor.sourceNotice || "";
    notice.hidden = !editor.sourceNotice;
    this.invalidate();
    this.showOutput();
  }

  setVisible(visible) {
    this.visible = visible;
    if (visible) this.showOutput();
  }

  showOutput() {
    const svg = this.output.value === "svg";
    document.getElementById("result").dataset.output = this.output.value;
    document.getElementById("markdown-controls").hidden = svg;
    document.getElementById("region").hidden = svg;
    document.getElementById("svg-output").hidden = !svg;
    if (svg && this.visible) this.refresh();
  }

  invalidate() {
    this.serial += 1;
    this.request?.abort();
    this.request = null;
    if (this.resource) URL.revokeObjectURL(this.resource.url);
    this.resource = null;
    this.image.hidden = true;
    this.image.removeAttribute("src");
    this.copy.disabled = true;
    this.download.disabled = true;
    this.copy.textContent = "Copy SVG";
    this.preview.setAttribute("aria-busy", "false");
    this.message("");
  }

  message(text, error = false) {
    this.status.textContent = text;
    this.status.dataset.error = String(error);
  }

  async changeAppearance() {
    const source = this.getEditor()?.state.generation;
    const appearance = { ...this.appearance, theme: this.theme.value };
    this.invalidate();
    this.theme.disabled = true;
    try {
      if (this.getEditor()?.sourceFormat === "svg") {
        const saved = await this.setAppearance(appearance);
        if (source !== this.getEditor()?.state.generation) return;
        this.appearance = this.getEditor().svgAppearance;
        if (!saved) this.message("Appearance could not be changed. Try again.", true);
      } else {
        this.appearance = appearance;
      }
      this.theme.value = this.appearance.theme;
    } finally {
      this.theme.disabled = false;
    }
    this.refresh();
  }

  async refresh() {
    const ticket = ++this.serial;
    const saved = await this.waitForEdits();
    if (ticket !== this.serial) return;
    if (!saved) {
      this.message("An edit could not be applied. Resolve it before exporting SVG.", true);
      return;
    }
    const editor = this.getEditor();
    if (!editor?.region) return;
    const settings = editor.state.curation.settings;
    const body = { region: editor.region, text_style: settings.style, show_counts: settings.show_counts, appearance: this.appearance };
    const key = JSON.stringify(body);
    if (this.resource?.key === key) return;
    this.request?.abort();
    const request = new AbortController();
    this.request = request;
    this.preview.setAttribute("aria-busy", "true");
    this.message("Preparing SVG…");
    try {
      const response = await fetch("/api/export/svg", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: key, signal: request.signal,
      });
      const result = await response.json();
      if (!response.ok || typeof result.svg !== "string") throw new Error(result.error?.message || "SVG could not be generated.");
      if (ticket !== this.serial || editor !== this.getEditor()) return;
      await this.display(result.svg, key, ticket);
    } catch (error) {
      if (ticket !== this.serial || request.signal.aborted) return;
      this.invalidate();
      this.message(`${error.message || "SVG could not be generated."} Change an option or reopen Export to try again.`, true);
    } finally {
      if (this.request === request) {
        this.request = null;
        this.preview.setAttribute("aria-busy", "false");
      }
    }
  }

  async display(svg, key, ticket) {
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    this.image.src = url;
    try {
      await this.image.decode();
    } catch (error) {
      URL.revokeObjectURL(url);
      throw error;
    }
    if (ticket !== this.serial) { URL.revokeObjectURL(url); return; }
    if (this.resource) URL.revokeObjectURL(this.resource.url);
    this.resource = { svg, key, url };
    this.image.hidden = false;
    this.copy.disabled = false;
    this.download.disabled = false;
    this.message("");
  }

  async deliver(action) {
    const editor = this.getEditor();
    const resource = this.resource;
    if (!resource) return;
    this.copy.disabled = true;
    this.download.disabled = true;
    try {
      const saved = await this.waitForEdits();
      if (!saved || editor !== this.getEditor() || resource !== this.resource) return;
      if (action === "copy") {
        await navigator.clipboard.writeText(resource.svg);
        if (resource !== this.resource) return;
        this.copy.textContent = "Copied";
        this.message("SVG source copied.");
      } else {
        const link = document.createElement("a");
        link.href = resource.url;
        link.download = editor.sourceFormat === "svg" ? displayPath(editor.document).split("/").pop() : "treestamp.svg";
        link.click();
        this.message("SVG download started.");
      }
    } catch (_) {
      this.message(action === "copy" ? "Copy failed. Download the SVG instead." : "Download failed. Try again or copy the SVG.", true);
    } finally {
      this.copy.disabled = !this.resource;
      this.download.disabled = !this.resource;
    }
  }
}
