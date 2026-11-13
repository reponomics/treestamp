// Pure-logic tests for the page; run with `node --test web/tests/js`.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  addressFor, decodeState, encodeState, hintFor, pathKey, displayPath,
  opBody, parseRoute, previewParams, preparePreview, regionSegments,
  rowName, rowSuffix, settingsFromValues, sourceSelection, treeNavigation, valuesFromQuery, valuesFromSettings,
} from "../../src/treestamp_web/static/logic.js";

const values = { style: "unicode", show_counts: true, root: " src ", document: "" };

test("tree navigation treats the root and non-directory entries like the TUI", () => {
  const rows = [
    { path: "", depth: 0, kind: "dir", files: 3, dirs: 0 },
    { path: "file", depth: 1, kind: "file" },
    { path: "link", depth: 1, kind: "symlink" },
    { path: "module", depth: 1, kind: "gitlink" },
  ];
  assert.deepEqual(treeNavigation(rows, [], 0, "ArrowLeft"), { index: 0 });
  assert.deepEqual(treeNavigation(rows, [], 0, " "), { index: 0 });
  assert.deepEqual(treeNavigation(rows, [], 0, "ArrowRight"), { index: 1 });
  for (const index of [1, 2, 3]) {
    assert.deepEqual(treeNavigation(rows, [], index, "ArrowRight"), { index });
    assert.deepEqual(treeNavigation(rows, [], index, " "), { index });
    assert.deepEqual(treeNavigation(rows, [], index, "ArrowLeft"), { index: 0 });
  }
  assert.deepEqual(treeNavigation(rows.slice(0, 1), [], 0, "ArrowRight"), { index: 0 });
});

test("tree navigation distinguishes actual folds from empty-looking directories", () => {
  const rows = [
    { path: "", depth: 0, kind: "dir", files: 0, dirs: 2 },
    { path: "hidden children", depth: 1, kind: "dir", files: 2, dirs: 0, collapsed: true },
    { path: "empty", depth: 1, kind: "dir", files: 0, dirs: 0, collapsed: true },
  ];
  const expanded = ["hidden children", "empty"];
  assert.deepEqual(treeNavigation(rows, expanded, 1, "ArrowRight"), { index: 1 });
  assert.deepEqual(treeNavigation(rows, expanded, 1, "ArrowLeft"), { index: 1, operation: "collapse" });
  assert.deepEqual(treeNavigation(rows, [], 1, "ArrowRight"), { index: 1, operation: "expand" });
  assert.deepEqual(treeNavigation(rows, [], 1, "ArrowLeft"), { index: 0 });
  assert.deepEqual(treeNavigation(rows, expanded, 2, "ArrowLeft"), { index: 0 });
  assert.deepEqual(treeNavigation(rows, expanded, 2, "ArrowRight"), { index: 2 });
});

test("vertical and page navigation stop at the first and last visible rows", () => {
  const rows = Array.from({ length: 12 }, (_, index) => ({ path: String(index) }));
  for (const [index, key, expected] of [
    [0, "ArrowUp", 0], [11, "ArrowDown", 11], [5, "ArrowDown", 6], [5, "ArrowUp", 4],
    [5, "Home", 0], [5, "End", 11], [5, "PageDown", 9], [5, "PageUp", 1],
    [9, "PageDown", 11], [1, "PageUp", 0],
  ]) {
    assert.deepEqual(treeNavigation(rows, [], index, key, 4), { index: expected });
  }
});





test("state survives the fragment, including non-ASCII, and garbage decodes to null", () => {
  const state = { curation: { settings: { root: "." }, expanded: ["src"], hidden: ["ünïcode.md"], annotations: [{ path: "", text: "root ✓" }] } };
  const encoded = encodeState(state);
  assert.match(encoded, /^[A-Za-z0-9_-]+$/);
  assert.deepEqual(decodeState(encoded), state);
  assert.equal(decodeState("not base64!"), null);
  assert.equal(decodeState(encodeState([1, 2])), null, "a non-object is not a state");
});

test("routes parse owner, repo, optional commit, and saved state", () => {
  const sha = "a".repeat(40);
  assert.deepEqual(parseRoute("/o/r", ""), { owner: "o", repo: "r", sha: null, saved: null });
  assert.deepEqual(parseRoute(`/o/r@${sha}/`, "#s=" + encodeState({ hidden: [] })), { owner: "o", repo: "r", sha, saved: { hidden: [] } });
  assert.equal(parseRoute("/", ""), null);
  assert.equal(parseRoute("/o/r@short", ""), null);
  assert.equal(parseRoute("/api/preview", "").owner, "api", "the server refuses reserved prefixes; the parser does not");
});

test("the address keeps path and query on this origin and appends the state", () => {
  const address = addressFor("https://elsewhere.example/o/r@abc?root=src", { x: 1 }, "http://127.0.0.1:8000");
  assert.equal(address, `/o/r@abc?root=src#s=${encodeState({ x: 1 })}`);
  assert.equal(addressFor("/o/r?root=.", {}, "http://h"), `/o/r?root=.#s=${encodeState({})}`);
});


test("hints follow the error table", () => {
  assert.match(hintFor("invalid_link", 400), /Accepted forms/);
  assert.match(hintFor("state_too_large", 413), /more folds/);
  assert.match(hintFor("not_found", 404), /default branch/);
  assert.match(hintFor("too_large", 413), /locally/);
  assert.match(hintFor("upstream_unavailable", 503), /budget/);
  assert.match(hintFor("curation", 422), /previous draft is unchanged/);
  assert.match(hintFor("snapshot_unavailable", 410), /Load the repository URL again/);
  assert.equal(hintFor("unexpected", 500), "");
});

test("directory shortcuts toggle nested rows and ignore unrelated keys", () => {
  const rows = [
    { path: "", depth: 0, kind: "dir", files: 0, dirs: 1 },
    { path: "src", depth: 1, kind: "dir", files: 1, dirs: 0 },
    { path: "src/main.py", depth: 2, kind: "file" },
  ];
  assert.deepEqual(treeNavigation(rows, ["src"], 1, " "), { index: 1, operation: "toggle" });
  assert.deepEqual(treeNavigation(rows, ["src"], 1, "ArrowRight"), { index: 2 });
  assert.deepEqual(treeNavigation(rows, ["src"], 2, "ArrowLeft"), { index: 1 });
  assert.deepEqual(treeNavigation(rows, [], 1, "Escape"), { index: 1 });
});

test("empty source fields and queries preserve their documented defaults", () => {
  assert.deepEqual(sourceSelection({}), { root: ".", document: "" });
  assert.deepEqual(sourceSelection({ root: "src", document: "" }, { root: "old" }), { root: "src", document: "" });
  assert.deepEqual(valuesFromQuery(new URLSearchParams()), {});
  assert.deepEqual(valuesFromQuery(new URLSearchParams("root=")), { root: "" });
  assert.deepEqual(valuesFromQuery(new URLSearchParams("document=")), { document: "" });
  assert.equal(displayPath({ git_bytes: "" }), "");
});

test("saved fragments reject scalar JSON and invalid UTF-8", () => {
  for (const value of [null, false, 42, "text"]) {
    assert.equal(decodeState(encodeState(value)), null);
  }
  assert.equal(decodeState(btoa(String.fromCharCode(0xff))), null);
  assert.deepEqual(parseRoute("/owner/repo", "#other=value"), { owner: "owner", repo: "repo", sha: null, saved: null });
});

test("partial regions preserve every byte even without closing markers", () => {
  for (const text of ["", "<!-- treestamp:start -->\n\n", "<!-- treestamp:start -->\n<!-- treestamp:config\nroot = \".\"\n./\n"]) {
    assert.equal(regionSegments(text).map(segment => segment.text).join(""), text);
  }
  assert.equal(rowSuffix({ kind: "symlink" }), "-> null");
});

test("region segments quiet the markers and config and reproduce the text exactly", () => {
  const full = '<!-- treestamp:start -->\n<!-- treestamp:config\nroot = "."\n-->\n```sh\n./\n└── src/\n```\n<!-- treestamp:end -->\n';
  const segments = regionSegments(full);
  assert.deepEqual(segments.map((s) => s.quiet), [true, false, true]);
  assert.equal(segments.map((s) => s.text).join(""), full);
  assert.equal(segments[0].text, '<!-- treestamp:start -->\n<!-- treestamp:config\nroot = "."\n-->\n');
  assert.equal(segments[2].text, "<!-- treestamp:end -->\n");
  const bare = "<!-- treestamp:start -->\n.\n<!-- treestamp:end -->";
  assert.equal(regionSegments(bare).map((s) => s.text).join(""), bare);
  assert.deepEqual(regionSegments(bare).map((s) => s.quiet), [true, false, true]);
  assert.equal(regionSegments("just a tree").map((s) => s.text).join(""), "just a tree");
});


test("rows print names and suffixes as the codec does", () => {
  assert.equal(rowName({ kind: "dir", path: "src", name: "src" }), "src/");
  assert.equal(rowName({ kind: "dir", path: "", name: "." }), "./");
  assert.equal(rowName({ kind: "file", path: "a.py", name: "a.py" }), "a.py");
  assert.equal(rowSuffix({ kind: "gitlink" }), "[gitlink]");
  assert.equal(rowSuffix({ kind: "symlink", target: "../docs/a b" }), "-> ../docs/a b");
  assert.equal(rowSuffix({ kind: "symlink", target: null }), "-> null");
  assert.equal(rowSuffix({ kind: "file" }), "");
});




test("new source parameters only select repository-relative root and document", () => {
  assert.deepEqual([...previewParams(values)], [["root", " src "], ["document", ""]]);
  assert.equal(previewParams({ root: "", document: "docs/README.md" }).get("root"), ".");
  assert.deepEqual(valuesFromQuery(new URLSearchParams("root=src&document=docs/README.md")), { root: "src", document: "docs/README.md" });
  for (const key of ["depth", "max_children", "count_mode", "hide_root_files", "style"]) {
    assert.throws(() => valuesFromQuery(new URLSearchParams(`${key}=x`)), /Unsupported/);
  }
});

test("one count toggle edits presentation and retains the selected root", () => {
  const settings = { root: "docs", style: "unicode", show_counts: true };
  assert.deepEqual(settingsFromValues(settings, { style: "list", show_counts: false }), { root: "docs", style: "list", show_counts: false, attribution: false });
  assert.deepEqual(valuesFromSettings(settings), { ...settings, attribution: false });
});

test("attribution defaults off for old drafts and survives form and shared state round trips", () => {
  const original = { root: "docs", style: "unicode", show_counts: true };
  const enabled = settingsFromValues(original, { ...valuesFromSettings(original), attribution: true });
  assert.deepEqual(enabled, { ...original, attribution: true });
  const restored = decodeState(encodeState({ settings: enabled })).settings;
  assert.equal(valuesFromSettings(restored).attribution, true);
  assert.deepEqual(settingsFromValues(restored, { ...valuesFromSettings(restored), attribution: false }), { ...original, attribution: false });
});

test("operation bodies retain the captured source and baseline while editing curation", () => {
  const state = { version: 1, source: { commit: "c".repeat(40) }, baseline: "saved", generation: "id", revision: 3, curation: { settings: {}, expanded: ["a"], hidden: [], annotations: [] } };
  const editor = { owner: "o", repo: "r", ref: "c".repeat(40), root: "src", document: "docs/README.md", state };
  const body = opBody(editor, { root: "src", style: "ascii", show_counts: true }, true, "annotate", "a", "note");
  assert.deepEqual(body.state, { ...state, curation: { ...state.curation, settings: { root: "src", style: "ascii", show_counts: true } } });
  assert.deepEqual(body.op, { type: "annotate", path: "a", text: "note" });
  assert.equal(body.ref, editor.ref);
  assert.deepEqual(opBody(editor, {}, false, "restore").op, { type: "restore", path: "", text: "" });
});

test("byte identities survive DOM keys and URL state without colliding with display text", () => {
  const identity = { git_bytes: "626164ff" };
  assert.equal(pathKey(identity), "/git/626164ff");
  assert.equal(pathKey("bad�"), "bad�");
  assert.equal(displayPath(identity), "bad�");
  const state = { curation: { hidden: [identity] } };
  assert.deepEqual(decodeState(encodeState(state)), state);
  const editor = { state: { curation: {} }, rows: [{ path: pathKey(identity), identity }] };
  assert.deepEqual(opBody(editor, {}, false, "hide", pathKey(identity)).op.path, identity);
  editor.rows = []; // Hiding removes the row, but Undo retains its DOM identity.
  assert.deepEqual(opBody(editor, {}, false, "unhide", pathKey(identity)).op.path, identity);
});


test("source selection preserves exact whitespace and unchanged byte identities", () => {
  const root = { git_bytes: "737263ff" };
  const document = { git_bytes: "646f63ff2e6d64" };
  assert.deepEqual(sourceSelection({ root: displayPath(root), document: displayPath(document) }, { root, document }), { root, document });
  assert.deepEqual(sourceSelection({ root: " src ", document: " README.md " }, { root, document }), { root: " src ", document: " README.md " });
  assert.deepEqual([...previewParams({ root: " src ", document: " README.md " })], [["root", " src "], ["document", " README.md "]]);
});


test("preview candidates validate before adoption, including bundled examples", async () => {
  const { EXAMPLES } = await import("../../src/treestamp_web/static/example.js");
  for (const data of Object.values(EXAMPLES)) {
    const prepared = preparePreview(data, "https://treestamp.reponomics.org");
    assert.equal(prepared.rows.length, data.rows.length);
    assert.ok(prepared.address.startsWith("/"));
    for (const mutate of [
      candidate => { candidate.region = null; },
      candidate => { candidate.state.curation.settings = null; },
      candidate => { candidate.state.curation.settings.attribution = "true"; },
      candidate => { candidate.rows[0].path = null; },
      candidate => { candidate.rows[0].depth = -1; },
    ]) {
      const candidate = structuredClone(data);
      mutate(candidate);
      assert.throws(() => preparePreview(candidate, "https://example.org"), /previous draft is unchanged/);
    }
  }
});

test("incomplete preview responses cannot replace the accepted draft", async () => {
  const { EXAMPLES } = await import("../../src/treestamp_web/static/example.js");
  const original = Object.values(EXAMPLES)[0];
  const invalidCandidates = [
    () => null,
    data => { data.region = "unmarked tree"; },
    data => { delete data.state; },
    data => { delete data.state.curation; },
    data => { data.state.curation.settings.style = "unknown"; },
    data => { data.state.curation.settings.show_counts = "true"; },
    data => { data.state.curation.settings.root = { git_bytes: "f" }; },
    data => { data.root = { git_bytes: "zz" }; },
    data => { data.document = {}; },
    data => { data.state.curation.hidden = null; },
    data => { delete data.repository; },
    data => { data.repository.owner = null; },
    data => { delete data.ref; },
    data => { data.permalink = null; },
    data => { data.rows = {}; },
    data => { data.rows = []; },
    data => { data.rows[0] = null; },
    data => { data.rows[0].name = null; },
    data => { data.rows[0].kind = "unknown"; },
    data => { data.rows[0].depth = 1.5; },
    data => { data.rows[0].depth = 1024; },
  ];
  for (const invalidate of invalidCandidates) {
    const data = structuredClone(original);
    const result = invalidate(data);
    const candidate = result === null ? null : data;
    assert.throws(() => preparePreview(candidate, "https://example.org"), /previous draft is unchanged/);
  }
});

test("preview byte paths retain identity while rows receive DOM keys", async () => {
  const { EXAMPLES } = await import("../../src/treestamp_web/static/example.js");
  const data = structuredClone(Object.values(EXAMPLES)[0]);
  const identity = { git_bytes: "737263ff" };
  data.root = identity;
  data.state.curation.settings.root = identity;
  delete data.state.curation.settings.attribution; // Older shared drafts omit this option.
  data.document = { git_bytes: "524541444d452e6d64" };
  data.rows[0].path = identity;
  const before = structuredClone(data);
  const prepared = preparePreview(data, "https://example.org");
  assert.equal(prepared.rows[0].path, "/git/737263ff");
  assert.deepEqual(prepared.rows[0].identity, identity);
  assert.deepEqual(data, before, "preparing a candidate must not mutate the response");
});

test("region metadata stays quiet across optional spacing and CRLF", () => {
  for (const gap of ["", "\n"]) {
    for (const eol of ["\n", "\r\n"]) {
      const text = (`<!-- treestamp:start -->\n${gap}<!-- treestamp:config\nroot = "src"\n-->\n${gap}\`\`\`sh\n./\n\`\`\`\n${gap}<!-- treestamp:end -->\n`).replace(/\n/g, eol);
      const segments = regionSegments(text);
      assert.equal(segments.map((segment) => segment.text).join(""), text);
      assert.deepEqual(segments.map((segment) => segment.quiet), [true, false, true]);
      assert.ok(segments[0].text.includes('root = "src"'));
      assert.ok(!segments[1].text.includes('root = "src"'));
      assert.ok(segments[1].text.includes("./"));
    }
  }
});
