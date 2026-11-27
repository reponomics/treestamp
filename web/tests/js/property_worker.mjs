// Answers generated browser-decoding cases from web/tests/test_properties_browser_decoding.py.
// One JSON request per line on stdin, one ASCII JSON response per line on stdout.
// Not a *.test.mjs file, so `node --test` does not collect it.
import { createInterface } from "node:readline";
import {
  capturedSession, decodeState, displayPath, encodeState, parseRoute, pathKey,
  preparePreview, valuesFromQuery, valuesFromSettings,
} from "../../src/treestamp_web/static/logic.js";
import { draftForLocation, readDraft, saveDraft } from "../../src/treestamp_web/static/draft.js";
import { EXAMPLES } from "../../src/treestamp_web/static/example.js";

function memoryStorage(value = null) {
  const entries = new Map(value === null ? [] : [["treestamp.current-draft", value]]);
  return { getItem: key => entries.get(key) ?? null, setItem: (key, item) => entries.set(key, item) };
}

// What the page reads from an accepted captured session before the service sees it.
function display(saved) {
  if (!capturedSession(saved)) return null;
  return {
    values: valuesFromSettings(saved.curation.settings),
    root: displayPath(saved.source.root),
    document: displayPath(saved.source.document),
  };
}

const CALLS = {
  decodeState: text => decodeState(text),
  roundTripState: state => decodeState(encodeState(state)),
  parseRoute: (pathname, hash) => parseRoute(pathname, hash),
  valuesFromQuery: query => valuesFromQuery(new URLSearchParams(query)),
  pathKey: value => pathKey(value),
  displayPath: value => displayPath(value),
  // The fragment journey: a link's saved state, as startup reads it.
  startup: (pathname, hash) => {
    const route = parseRoute(pathname, hash);
    return { route: route !== null, shown: route?.saved && route.sha ? display(route.saved) : null };
  },
  // The localStorage journey: a stored record, and the session the user may resume.
  draft: (stored, location) => {
    const storage = memoryStorage(stored);
    const read = readDraft(storage);
    const offered = draftForLocation(location, storage);
    let shown = null;
    if (offered) {
      const address = new URL(offered.address, "https://treestamp.invalid");
      shown = display(parseRoute(address.pathname, address.hash).saved);
    }
    return { read, offered, shown };
  },
  saveAndRead: (address, now) => {
    const storage = memoryStorage();
    return { saved: saveDraft(address, storage, now), read: readDraft(storage) };
  },
  preparePreview: (data, origin) => preparePreview(data, origin),
  // A service-shaped preview response, from the page's bundled example.
  example: () => structuredClone(Object.values(EXAMPLES)[0]),
};

const prototypeKeys = () => Object.getOwnPropertyNames(Object.prototype).sort().join();
const pristine = prototypeKeys();

function ascii(value) {
  return JSON.stringify(value).replace(/[\u007f-\uffff]/g, c => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`);
}

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of lines) {
  let response;
  try {
    const { call, args } = JSON.parse(line);
    response = { ok: true, value: CALLS[call](...args) ?? null };
  } catch (error) {
    response = { ok: false, error: { type: error?.constructor?.name ?? typeof error, message: String(error?.message ?? error) } };
  }
  response.prototype = prototypeKeys() === pristine && ({}).polluted === undefined;
  let text;
  try {
    text = ascii(response);
  } catch (error) {
    // A value too deep to serialize is reported by kind, not by content.
    text = ascii({ ...response, value: { unserializable: error.constructor.name } });
  }
  process.stdout.write(`${text}\n`);
}
