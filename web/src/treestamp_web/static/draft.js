// One accepted editing session for a short return journey in this browser.
// Snapshot availability still belongs to the service; this is not a backup.
import { isDisplayableSession, parseRoute, valuesFromQuery } from "./logic.js";

export const DRAFT_KEY = "treestamp.current-draft";
const LOCAL_ORIGIN = "https://treestamp.invalid";
const REPOSITORY_PATH = /^\/[A-Za-z0-9][A-Za-z0-9-]*\/[A-Za-z0-9_.-]+@[0-9a-f]{40}$/;

function localSessionURL(address) {
  if (typeof address !== "string" || /[\\\u0000-\u0020]/.test(address)) return null;
  const url = new URL(address, LOCAL_ORIGIN);
  if (url.origin !== LOCAL_ORIGIN || url.pathname + url.search + url.hash !== address) return null;
  if (!REPOSITORY_PATH.test(url.pathname)) return null;
  valuesFromQuery(url.searchParams);
  return url;
}

function capturedRoute(address) {
  const url = localSessionURL(address);
  if (!url) return null;
  const route = parseRoute(url.pathname, url.hash);
  if (!isDisplayableSession(route?.saved)) return null;
  const source = route.saved.source;
  if (source.owner !== route.owner || source.repo !== route.repo || source.commit !== route.sha) return null;
  return route;
}

function validRecord(record) {
  return record?.version === 1
    && Number.isFinite(record.savedAt)
    && record.savedAt >= 0
    && capturedRoute(record.address) !== null;
}

export function readDraft(storage) {
  try {
    const record = JSON.parse((storage ?? globalThis.localStorage).getItem(DRAFT_KEY));
    return validRecord(record) ? record : null;
  } catch (_) {
    return null;
  }
}

export function saveDraft(address, storage, now = Date.now()) {
  try {
    const record = { version: 1, address, savedAt: now };
    if (!validRecord(record)) return false;
    (storage ?? globalThis.localStorage).setItem(DRAFT_KEY, JSON.stringify(record));
    return true;
  } catch (_) {
    return false;
  }
}

export function draftForLocation(location, storage) {
  // Explicit settings and captured links always win over browser history.
  if (location.search || location.hash) return null;
  const draft = readDraft(storage);
  if (!draft) return null;
  if (location.pathname === "/") return draft;
  const route = parseRoute(location.pathname, "");
  if (!route || route.sha) return null;
  const saved = capturedRoute(draft.address);
  const sameRepository = route.owner.toLowerCase() === saved.owner.toLowerCase()
    && route.repo.toLowerCase() === saved.repo.toLowerCase();
  return sameRepository ? draft : null;
}
