/**
 * Chrome storage wrapper — typed async helpers.
 * Uses chrome.storage.local for all persistent state.
 */
import type { StoredState, AuthState } from "./types";
import { DEFAULT_BACKEND_URL } from "./types";

export const DEFAULT_STATE: StoredState = {
  auth: { accessToken: null, refreshToken: null, user: null },
  backendUrl: DEFAULT_BACKEND_URL,
  currentWorkspaceId: null,
  currentMeetingId: null,
  detectedMeeting: null,
  botStatus: "idle",
  sessionStatus: "inactive",
};

export async function getStoredState(): Promise<StoredState> {
  return new Promise((resolve) => {
    chrome.storage.local.get(null, (items) => {
      resolve({ ...DEFAULT_STATE, ...items } as StoredState);
    });
  });
}

export async function setStoredState(partial: Partial<StoredState>): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.set(partial, resolve);
  });
}

export async function getAuth(): Promise<AuthState> {
  const state = await getStoredState();
  return state.auth;
}

export async function setAuth(auth: AuthState): Promise<void> {
  await setStoredState({ auth });
}

export async function clearAuth(): Promise<void> {
  await setStoredState({
    auth: { accessToken: null, refreshToken: null, user: null },
    currentWorkspaceId: null,
    currentMeetingId: null,
    sessionStatus: "inactive",
    botStatus: "idle",
  });
}

export async function getBackendUrl(): Promise<string> {
  const state = await getStoredState();
  return state.backendUrl || DEFAULT_BACKEND_URL;
}

export async function setBackendUrl(url: string): Promise<void> {
  await setStoredState({ backendUrl: url.replace(/\/$/, "") });
}

/** Listen for storage changes and call back with the new state fields. */
export function onStorageChange(
  keys: (keyof StoredState)[],
  callback: (changes: Partial<StoredState>) => void
): () => void {
  const handler = (changes: Record<string, chrome.storage.StorageChange>) => {
    const relevant: Partial<StoredState> = {};
    let hasRelevant = false;
    for (const key of keys) {
      if (key in changes) {
        (relevant as Record<string, unknown>)[key] = changes[key].newValue;
        hasRelevant = true;
      }
    }
    if (hasRelevant) callback(relevant);
  };
  chrome.storage.onChanged.addListener(handler);
  return () => chrome.storage.onChanged.removeListener(handler);
}
