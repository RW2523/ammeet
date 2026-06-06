import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User, Workspace } from "./types";

interface AuthState {
  user: User | null;
  accessToken: string | null;
  setAuth: (user: User, accessToken: string, refreshToken: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      setAuth: (user, accessToken, refreshToken) => {
        if (typeof window !== "undefined") {
          localStorage.setItem("access_token", accessToken);
          localStorage.setItem("refresh_token", refreshToken);
        }
        set({ user, accessToken });
      },
      clearAuth: () => {
        if (typeof window !== "undefined") {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
        }
        set({ user: null, accessToken: null });
      },
    }),
    { name: "ammeet-auth", partialize: (s) => ({ user: s.user }) }
  )
);

interface WorkspaceState {
  current: Workspace | null;
  setCurrent: (ws: Workspace | null) => void;
}

export const useWorkspaceStore = create<WorkspaceState>()((set) => ({
  current: null,
  setCurrent: (ws) => set({ current: ws }),
}));
