/**
 * AmMeeting Backend API client for the Chrome extension.
 * All calls go through the configured backend URL stored in chrome.storage.
 */
import type {
  AuthState,
  WorkspaceInfo,
  MeetingInfo,
  Question,
} from "./types";

export class ApiClient {
  constructor(
    private baseUrl: string,
    private accessToken: string | null = null
  ) {}

  setToken(token: string | null) {
    this.accessToken = token;
  }

  private get headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.accessToken) h["Authorization"] = `Bearer ${this.accessToken}`;
    return h;
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}/api${path}`;
    const resp = await fetch(url, {
      ...options,
      headers: { ...this.headers, ...(options?.headers ?? {}) },
    });

    if (resp.status === 401) throw new ApiError(401, "Unauthorized");
    if (!resp.ok) {
      const text = await resp.text().catch(() => "Unknown error");
      throw new ApiError(resp.status, text);
    }

    const contentType = resp.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return resp.json() as Promise<T>;
    }
    return resp.text() as unknown as T;
  }

  // ── Auth ───────────────────────────────────────────────────────────────────

  async login(email: string, password: string): Promise<{ access_token: string; refresh_token: string }> {
    return this.request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  }

  async getMe(): Promise<{ id: string; email: string; full_name: string }> {
    return this.request("/auth/me");
  }

  async refreshToken(refreshToken: string): Promise<{ access_token: string }> {
    return this.request("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  }

  // ── Workspaces ────────────────────────────────────────────────────────────

  async getWorkspaces(): Promise<WorkspaceInfo[]> {
    return this.request<WorkspaceInfo[]>("/workspaces");
  }

  // ── Meetings ──────────────────────────────────────────────────────────────

  async getMeetings(workspaceId: string): Promise<MeetingInfo[]> {
    return this.request<MeetingInfo[]>(`/workspaces/${workspaceId}/meetings`);
  }

  async getMeeting(workspaceId: string, meetingId: string): Promise<MeetingInfo> {
    return this.request<MeetingInfo>(`/workspaces/${workspaceId}/meetings/${meetingId}`);
  }

  // ── Questions ─────────────────────────────────────────────────────────────

  async getQuestions(workspaceId: string, meetingId: string): Promise<Question[]> {
    return this.request<Question[]>(`/workspaces/${workspaceId}/meetings/${meetingId}/questions`);
  }

  async generateQuestions(workspaceId: string, meetingId: string): Promise<{ generated: number }> {
    return this.request(`/workspaces/${workspaceId}/meetings/${meetingId}/generate-questions`, {
      method: "POST",
    });
  }

  // ── Live Session ──────────────────────────────────────────────────────────

  async joinMeeting(
    workspaceId: string,
    meetingId: string,
    meetingUrl: string,
    simulate = false
  ): Promise<{ status: string; questions_queued: number }> {
    return this.request(`/workspaces/${workspaceId}/meetings/${meetingId}/bot/join`, {
      method: "POST",
      body: JSON.stringify({ meeting_url: meetingUrl, simulate }),
    });
  }

  async leaveMeeting(workspaceId: string, meetingId: string): Promise<{ status: string }> {
    return this.request(`/workspaces/${workspaceId}/meetings/${meetingId}/bot/leave`, {
      method: "POST",
    });
  }

  async getBotStatus(workspaceId: string, meetingId: string): Promise<{ status: string }> {
    return this.request(`/workspaces/${workspaceId}/meetings/${meetingId}/bot/status`);
  }

  async generateReport(workspaceId: string, meetingId: string): Promise<{ id: string; summary: string }> {
    return this.request(`/workspaces/${workspaceId}/meetings/${meetingId}/reports/generate`, {
      method: "POST",
    });
  }

  async queryKnowledge(workspaceId: string, query: string): Promise<{ answer: string }> {
    return this.request(`/workspaces/${workspaceId}/knowledge/query`, {
      method: "POST",
      body: JSON.stringify({ query, limit: 5 }),
    });
  }

  // ── Transcription ─────────────────────────────────────────────────────────

  async transcribeAudio(
    workspaceId: string,
    meetingId: string,
    audioBlob: Blob,
    filename = "recording.webm"
  ): Promise<{ transcript: string }> {
    const form = new FormData();
    form.append("audio_file", audioBlob, filename);
    const url = `${this.baseUrl}/api/workspaces/${workspaceId}/meetings/${meetingId}/transcribe-audio`;
    const resp = await fetch(url, {
      method: "POST",
      headers: this.accessToken ? { Authorization: `Bearer ${this.accessToken}` } : {},
      body: form,
    });
    if (!resp.ok) throw new ApiError(resp.status, await resp.text());
    return resp.json();
  }

  // ── TTS ───────────────────────────────────────────────────────────────────

  async synthesizeSpeech(workspaceId: string, text: string): Promise<ArrayBuffer> {
    const resp = await fetch(`${this.baseUrl}/api/workspaces/${workspaceId}/tts`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify({ text, voice: "nova" }),
    });
    if (!resp.ok) throw new ApiError(resp.status, await resp.text());
    return resp.arrayBuffer();
  }

  /** Build the WebSocket URL for a meeting's real-time event stream. */
  getWebSocketUrl(meetingId: string): string {
    const base = this.baseUrl.replace(/^http/, "ws");
    return `${base}/api/ws/meetings/${meetingId}`;
  }
}

export class ApiError extends Error {
  constructor(
    public statusCode: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}
