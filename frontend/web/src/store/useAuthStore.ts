import { create } from 'zustand';
import { API_V1, apiPostJson, ApiError } from '../lib/apiClient';

/**
 * Auth client store (Plan 3 A9).
 *
 * Holds the JWT in localStorage so it survives page reloads. The token is
 * read by ``apiClient`` via the global hook below. Sign-up and login both
 * return ``AuthResponse``; we cache the user + token together so the UI
 * doesn't need a follow-up "who am I" call on success.
 */
const TOKEN_KEY = 'synesthesia.auth.token';
const USER_KEY = 'synesthesia.auth.user';

interface AuthUser {
  user_id: string;
  username: string;
}

interface AuthResponse {
  token: string;
  user_id: string;
  username: string;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  loading: boolean;
  error: string | null;

  loadFromStorage: () => void;
  signup: (username: string, password: string) => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

function readStorage<T>(key: string): T | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function writeStorage(token: string | null, user: AuthUser | null) {
  if (typeof window === 'undefined') return;
  if (token) window.localStorage.setItem(TOKEN_KEY, JSON.stringify(token));
  else window.localStorage.removeItem(TOKEN_KEY);
  if (user) window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  else window.localStorage.removeItem(USER_KEY);
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  loading: false,
  error: null,

  loadFromStorage: () => {
    const token = readStorage<string>(TOKEN_KEY);
    const user = readStorage<AuthUser>(USER_KEY);
    set({ token, user });
  },

  signup: async (username, password) => {
    set({ loading: true, error: null });
    try {
      const res = await apiPostJson<AuthResponse>('/auth/signup', { username, password });
      writeStorage(res.token, { user_id: res.user_id, username: res.username });
      set({ token: res.token, user: { user_id: res.user_id, username: res.username }, loading: false });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Sign-up failed';
      set({ error: message, loading: false });
      throw err;
    }
  },

  login: async (username, password) => {
    set({ loading: true, error: null });
    try {
      const res = await apiPostJson<AuthResponse>('/auth/login', { username, password });
      writeStorage(res.token, { user_id: res.user_id, username: res.username });
      set({ token: res.token, user: { user_id: res.user_id, username: res.username }, loading: false });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Login failed';
      set({ error: message, loading: false });
      throw err;
    }
  },

  logout: () => {
    writeStorage(null, null);
    set({ token: null, user: null, error: null });
  },
}));

/** Returns the current bearer token, or null. Safe to call outside React. */
export function getAuthToken(): string | null {
  return useAuthStore.getState().token;
}

// Hint to readers: the apiClient could read getAuthToken() and inject an
// Authorization header automatically once the backend flips REQUIRE_AUTH=true.
// API_V1 is exported here only to document the relationship.
export const _AUTH_API_HINT = API_V1;
