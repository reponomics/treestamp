// Pure decisions for the page: no DOM, no fetch. Tested with `node --test`.

export const DEFAULT_DOCUMENT = "README.md";
export const ACCEPTED = "Accepted forms: owner/repo, github.com/owner/repo, or any https://github.com/owner/repo link. The editor reads the default branch.";

// ---------- keyboard navigation (matches the TUI's Cursor)

function treeParent(rows, index, expanded) {
  const row = rows[index];
  if (row.path && row.files + row.dirs > 0 && expanded.includes(row.path)) {
    return { index, operation: "collapse" };
  }
  for (let parent = index - 1; parent >= 0; parent--) {
    if (rows[parent].depth < row.depth) return { index: parent };
  }
  return { index };
}

function treeChild(rows, index, expanded) {
  const row = rows[index];
  if (row.path && !expanded.includes(row.path)) return { index, operation: "expand" };
  const child = rows[index + 1];
  return { index: child && child.depth > row.depth ? index + 1 : index };
}

export function treeNavigation(rows, expanded, index, key, pageSize = 1) {
  const steps = { ArrowUp: -1, ArrowDown: 1, Home: -rows.length, End: rows.length, PageUp: -pageSize, PageDown: pageSize };
  if (key in steps) return { index: Math.max(0, Math.min(rows.length - 1, index + steps[key])) };
  if (key === "ArrowLeft") return treeParent(rows, index, expanded);
  const row = rows[index];
  if (row.kind !== "dir") return { index };
  if (key === " " && row.path) return { index, operation: "toggle" };
  if (key === "ArrowRight") return treeChild(rows, index, expanded);
  return { index };
}

// ---------- settings

// Source selection belongs to Open/New; presentation changes edit the draft.
export function previewParams(values) {
  const params = new URLSearchParams();
  params.set("root", String(values.root || "."));
  params.set("document", String(values.document || ""));
  return params;
}

// An unchanged display of a byte path retains the complete source identity.
export function sourceSelection(values, original = {}) {
  const preserve = (text, path) => path && typeof path !== "string" && text === displayPath(path) ? path : text;
  return {
    root: preserve(String(values.root || "."), original.root),
    document: preserve(String(values.document || ""), original.document),
  };
}

export function settingsFromValues(base, values) {
  return { ...base, style: values.style, show_counts: Boolean(values.show_counts) };
}

export function valuesFromQuery(query) {
  for (const key of query.keys()) {
    if (!["root", "document"].includes(key)) throw new Error(`Unsupported document option: ${key}`);
  }
  const values = {};
  if (query.has("root")) values.root = query.get("root");
  if (query.has("document")) values.document = query.get("document");
  return values;
}

export function valuesFromSettings(settings) {
  return { root: displayPath(settings.root), style: settings.style, show_counts: settings.show_counts };
}

// A DOM identity is independent of replacement characters in a displayed byte name.
export function pathKey(value) {
  return typeof value === "string" ? value : `/git/${value.git_bytes}`;
}

export function displayPath(value) {
  if (typeof value === "string") return value;
  return new TextDecoder().decode(Uint8Array.from(value.git_bytes.match(/../g) || [], hex => parseInt(hex, 16)));
}

// ---------- state in the URL fragment

export function encodeState(state) {
  const bytes = new TextEncoder().encode(JSON.stringify(state));
  let binary = "";
  bytes.forEach((b) => { binary += String.fromCharCode(b); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function decodeState(text) {
  try {
    const binary = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    const parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch (_) {
    return null;
  }
}

// /owner/repo, /owner/repo@sha, with optional #s=state.
export function parseRoute(pathname, hash) {
  const match = pathname.match(/^\/([^/@]+)\/([^/@]+)(?:@([0-9a-f]{40}))?\/?$/);
  if (!match) return null;
  const saved = hash.startsWith("#s=") ? decodeState(hash.slice(3)) : null;
  return { owner: match[1], repo: match[2], sha: match[3] || null, saved };
}

// The address to show for a response: path and query only, on this origin.
export function addressFor(permalink, state, origin) {
  const target = new URL(permalink, origin);
  return `${target.pathname}${target.search}#s=${encodeState(state)}`;
}

// Validate a complete candidate before the page replaces its accepted draft.
function validPath(value) {
  return typeof value === "string" || Boolean(value && typeof value.git_bytes === "string" && /^(?:[0-9a-f]{2})+$/.test(value.git_bytes));
}

function validRow(row) {
  return row && validPath(row.path) && typeof row.name === "string"
    && ["dir", "file", "symlink", "gitlink"].includes(row.kind)
    && Number.isInteger(row.depth) && row.depth >= 0 && row.depth < 1024;
}

function validatePreviewOutput(data) {
  if (!data || typeof data.region !== "string" || !data.region.startsWith("<!-- treestamp:start")) {
    throw new Error("The replacement tree has no valid output. Your previous draft is unchanged.");
  }
}

function validatePreviewSettings(data) {
  const paths = data?.state?.curation;
  const settings = paths?.settings;
  if (!settings || !["unicode", "ascii", "list"].includes(settings.style) || typeof settings.show_counts !== "boolean"
      || !validPath(settings.root) || !validPath(data.root) || !validPath(data.document)
      || ![paths.expanded, paths.hidden, paths.annotations].every(Array.isArray)) {
    throw new Error("The replacement tree has invalid editing settings. Your previous draft is unchanged.");
  }
}

function validatePreviewSource(data) {
  if (!data.repository || ![data.repository.owner, data.repository.name, data.repository.url, data.ref?.commit, data.permalink].every(value => typeof value === "string")
      || !Array.isArray(data.rows) || !data.rows.length || !data.rows.every(validRow)) {
    throw new Error("The replacement tree is incomplete. Your previous draft is unchanged.");
  }
}

export function preparePreview(data, origin) {
  validatePreviewOutput(data);
  validatePreviewSettings(data);
  validatePreviewSource(data);
  return {
    rows: data.rows.map(row => ({ ...row, identity: row.path, path: pathKey(row.path) })),
    address: addressFor(data.permalink, data.state, origin),
  };
}

// ---------- requests

function pathIdentity(key) {
  return key?.startsWith("/git/") ? { git_bytes: key.slice(5) } : key || "";
}

export function opBody(editor, settings, reveal, type, path, text) {
  return {
    owner: editor.owner,
    repo: editor.repo,
    ref: editor.ref,
    root: editor.root,
    document: editor.document,
    state: { ...editor.state, curation: { ...editor.state.curation, settings } },
    reveal: Boolean(reveal),
    op: { type, path: editor.rows?.find(row => row.path === path)?.identity ?? pathIdentity(path), text: text || "" },
  };
}

// ---------- messages

export function hintFor(code, status) {
  if (code === "snapshot_unavailable") return "This temporary snapshot has expired or was evicted. Load the repository URL again to open its current public HEAD.";
  if (code === "curation") return "Your previous draft is unchanged. Check the reported entry or choose another subtree.";
  if (status === 400 && code === "invalid_link") return ACCEPTED;
  if (code === "state_too_large") return "This tree has more folds, hidden entries, and notes than the editor can send at once.";
  if (status === 404) return "Only public repositories can be opened, and only their default branch. Check the spelling.";
  if (status === 413) return "Large repositories can be curated locally with the treestamp command instead.";
  if (status === 503) return "GitHub is unavailable or the shared request budget is used up. Try again in a few minutes.";
  return "";
}

// ---------- the output region

// The region as display segments: the marker and config lines are quiet, the tree is not.
// Concatenating the segments' text reproduces the input exactly; only emphasis differs.
export function regionSegments(text) {
  const lines = text.split("\n");
  let headEnd = Math.min(1, lines.length);
  if (lines[1] && lines[1].startsWith("<!-- treestamp:config")) {
    const close = lines.indexOf("-->", 1);
    headEnd = close === -1 ? 1 : close + 1;
  }
  let tailStart = lines.length;
  for (let i = lines.length - 1; i >= headEnd; i--) {
    if (lines[i].startsWith("<!-- treestamp:end")) { tailStart = i; break; }
  }
  const join = (from, to) => lines.slice(from, to).join("\n") + (to < lines.length && to > from ? "\n" : "");
  return [
    { text: join(0, headEnd), quiet: true },
    { text: join(headEnd, tailStart), quiet: false },
    { text: lines.slice(tailStart).join("\n"), quiet: true },
  ].filter((segment) => segment.text);
}

// ---------- rows

export function rowName(row) {
  return row.kind === "dir" ? `${row.name}/` : row.name;
}

export function rowSuffix(row) {
  if (row.kind === "gitlink") return "[gitlink]";
  if (row.kind === "symlink") return `-> ${row.target === null || row.target === undefined ? "null" : row.target}`;
  return "";
}
