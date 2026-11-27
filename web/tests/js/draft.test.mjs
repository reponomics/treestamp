import { test } from "node:test";
import assert from "node:assert/strict";
import { DRAFT_KEY, draftForLocation, readDraft, saveDraft } from "../../src/treestamp_web/static/draft.js";
import { encodeState } from "../../src/treestamp_web/static/logic.js";

function memoryStorage() {
  const entries = new Map();
  return {
    getItem: key => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, value),
  };
}

function capturedState(owner = "pallets", repo = "flask", root = ".") {
  return {
    source: { owner, repo, commit: "a".repeat(40), root, document: "" },
    curation: {
      settings: { root, style: "unicode", show_counts: true, attribution: false },
      annotations: [{ path: "", text: "Remember this ✓" }],
    },
  };
}

function address(owner = "pallets", repo = "flask", root = ".", state = capturedState(owner, repo, root)) {
  return `/${owner}/${repo}@${"a".repeat(40)}?root=${encodeURIComponent(root)}&document=#s=${encodeState(state)}`;
}

const landing = { pathname: "/", search: "", hash: "" };

test("the latest accepted session replaces the one current draft", () => {
  const storage = memoryStorage();
  assert.equal(readDraft(storage), null);
  assert.equal(saveDraft(address(), storage, 100), true);
  assert.deepEqual(readDraft(storage), { version: 1, address: address(), savedAt: 100 });
  const replacement = address("other", "repository", "nested/folder");
  assert.equal(saveDraft(replacement, storage, 200), true);
  assert.equal(readDraft(storage).address, replacement);
});

test("returning to the app or the matching bare repository restores the current draft", () => {
  const storage = memoryStorage();
  saveDraft(address(), storage);
  for (const pathname of ["/", "/pallets/flask", "/Pallets/Flask/"]) {
    assert.equal(draftForLocation({ ...landing, pathname }, storage).address, address());
  }
  assert.equal(draftForLocation({ ...landing, pathname: "/other/repository" }, storage), null);
  assert.equal(draftForLocation({ ...landing, pathname: "/not-a-route" }, storage), null);
});

test("explicit settings, captured links, and hash links take precedence over the saved draft", () => {
  const storage = memoryStorage();
  saveDraft(address(), storage);
  for (const location of [
    { ...landing, search: "?root=src" },
    { ...landing, hash: "#anything" },
    { ...landing, pathname: "/pallets/flask", search: "?document=README.md" },
    { ...landing, pathname: `/pallets/flask@${"b".repeat(40)}` },
  ]) assert.equal(draftForLocation(location, storage), null);
});

test("corrupt, unsupported, or incomplete saved records do not interrupt startup", () => {
  const storage = memoryStorage();
  for (const value of ["not JSON", "null", "[]", "{}", ...[
    { version: 2, address: address(), savedAt: 10 },
    { version: 1, address: address(), savedAt: "10" },
    { version: 1, address: address(), savedAt: -1 },
    { version: 1, address: "/pallets/flask", savedAt: 10 },
  ].map(JSON.stringify)]) {
    storage.setItem(DRAFT_KEY, value);
    assert.equal(readDraft(storage), null);
    assert.equal(draftForLocation(landing, storage), null);
  }
});

test("saved addresses must be local captured sessions with matching source identity", () => {
  const storage = memoryStorage();
  const valid = address();
  saveDraft(valid, storage);
  const bad = [
    `https://elsewhere.example${valid}`, `//elsewhere.example${valid}`,
    `https://treestamp.invalid${valid}`, `/\\elsewhere.example${valid}`,
    `/../${valid}`, `${valid}\n`, valid.replace("/pallets/flask@", "/pallets/another@"),
    valid.replace("?root=", "?unsupported="),
    `/pallets/flask@${"a".repeat(40)}#s=${encodeState({ source: {}, curation: {} })}`,
    `/pallets/flask@${"a".repeat(40)}#s=invalid`,
  ];
  for (const candidate of bad) {
    assert.equal(saveDraft(candidate, storage), false, candidate);
    assert.equal(readDraft(storage).address, valid, "rejected input preserves the accepted record");
  }
});

test("drafts whose settings or source paths cannot be displayed are never offered", () => {
  // The browser would throw converting these for display before the service saw them.
  const storage = memoryStorage();
  const variants = [
    state => { state.curation.settings.root = null; },
    state => { delete state.curation.settings.root; },
    state => { state.curation.settings.root = { git_bytes: 7 }; },
    state => { state.curation.settings.root = { git_bytes: "zz" }; },
    state => { state.curation.settings = []; },
    state => { state.curation.settings.style = "list"; },
    state => { state.curation.settings.show_counts = "yes"; },
    state => { state.source.root = null; },
    state => { state.source.document = {}; },
  ];
  for (const change of variants) {
    const state = capturedState();
    change(state);
    const record = { version: 1, address: address("pallets", "flask", ".", state), savedAt: 10 };
    storage.setItem(DRAFT_KEY, JSON.stringify(record));
    assert.equal(readDraft(storage), null, String(change));
    assert.equal(draftForLocation(landing, storage), null, String(change));
  }
});

test("disabled or full browser storage leaves callers able to continue", () => {
  const blocked = {
    getItem() { throw new Error("Denied"); },
    setItem() { throw new Error("Quota exceeded"); },
  };
  assert.equal(readDraft(blocked), null);
  assert.equal(saveDraft(address(), blocked), false);
  assert.equal(draftForLocation(landing, blocked), null);
});

test("a blocked localStorage getter is caught as well as storage method failures", () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", { configurable: true, get() { throw new Error("Blocked"); } });
  try {
    assert.equal(readDraft(), null);
    assert.equal(saveDraft(address()), false);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete globalThis.localStorage;
  }
});
