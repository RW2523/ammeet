import { api } from "./api";
import type { ActionItem, CalendarEvent, Meeting, Person, PrepBrief, Question, Report, User, Workspace } from "./types";

// Auth
export const authApi = {
  register: (data: { email: string; password: string; full_name: string }) =>
    api.post<User>("/auth/register", data).then((r) => r.data),
  login: (data: { email: string; password: string; totp_code?: string }) =>
    api.post<{ access_token: string; refresh_token: string }>("/auth/login", data).then((r) => r.data),
  me: () => api.get<User>("/auth/me").then((r) => r.data),
  setupMfa: () => api.post<{ secret: string; uri: string }>("/auth/mfa/setup").then((r) => r.data),
  verifyMfa: (code: string) => api.post("/auth/mfa/verify", { code }).then((r) => r.data),
  verifyEmail: (token: string) =>
    api.post<{ verified: boolean }>("/auth/verify-email", { token }).then((r) => r.data),
  resendVerification: (email: string) =>
    api.post<{ sent: boolean }>("/auth/resend-verification", { email }).then((r) => r.data),
  forgotPassword: (email: string) =>
    api.post<{ sent: boolean }>("/auth/forgot-password", { email }).then((r) => r.data),
  resetPassword: (token: string, new_password: string) =>
    api.post<{ reset: boolean }>("/auth/reset-password", { token, new_password }).then((r) => r.data),
};

// Billing
export interface BillingInfo {
  plan: string;
  subscription_status: string | null;
  current_period_end: string | null;
  billing_enabled: boolean;
  usage: Record<string, { used: number; limit: number | null }>;
  plans: { id: string; price_usd_monthly: number; limits: Record<string, number | null> }[];
}

export const billingApi = {
  get: (workspaceId: string) =>
    api.get<BillingInfo>(`/workspaces/${workspaceId}/billing`).then((r) => r.data),
  checkout: (workspaceId: string, plan: string) =>
    api.post<{ mock: boolean; plan?: string; checkout_url: string | null }>(
      `/workspaces/${workspaceId}/billing/checkout`, { plan }
    ).then((r) => r.data),
  portal: (workspaceId: string) =>
    api.post<{ portal_url: string }>(`/workspaces/${workspaceId}/billing/portal`).then((r) => r.data),
};

// Workspaces
export const workspaceApi = {
  list: () => api.get<Workspace[]>("/workspaces").then((r) => r.data),
  get: (id: string) => api.get<Workspace>(`/workspaces/${id}`).then((r) => r.data),
  create: (data: { name: string; description?: string }) =>
    api.post<Workspace>("/workspaces", data).then((r) => r.data),
};

// People
export const peopleApi = {
  list: (workspaceId: string) =>
    api.get<Person[]>(`/workspaces/${workspaceId}/people`).then((r) => r.data),
  create: (workspaceId: string, data: Partial<Person>) =>
    api.post<Person>(`/workspaces/${workspaceId}/people`, data).then((r) => r.data),
  update: (workspaceId: string, personId: string, data: Partial<Person>) =>
    api.patch<Person>(`/workspaces/${workspaceId}/people/${personId}`, data).then((r) => r.data),
  delete: (workspaceId: string, personId: string) =>
    api.delete(`/workspaces/${workspaceId}/people/${personId}`),
};

// LLM / AI model settings
export interface LLMProviderInfo {
  id: string;
  label: string;
  default_model: string;
  models: string[];
  default_base_url: string;
  supports_embeddings: boolean;
  key_hint: string;
}

export interface LLMConfigInfo {
  provider: string;
  model: string;
  embedding_model: string | null;
  base_url: string | null;
  has_key: boolean;
  key_preview: string | null;
  source: string;
}

export const llmApi = {
  providers: () =>
    api.get<{ providers: LLMProviderInfo[] }>("/llm/providers").then((r) => r.data.providers),
  getConfig: () => api.get<LLMConfigInfo>("/llm/config").then((r) => r.data),
  setConfig: (data: {
    provider: string;
    model?: string;
    api_key?: string;
    embedding_model?: string;
    base_url?: string;
  }) => api.put("/llm/config", data).then((r) => r.data),
  test: () =>
    api.post<{ ok: boolean; provider?: string; model?: string; sample?: string; error?: string }>(
      "/llm/test"
    ).then((r) => r.data),
};

// Calendar
export const calendarApi = {
  events: (workspaceId: string) =>
    api.get<CalendarEvent[]>(`/workspaces/${workspaceId}/calendar/events`).then((r) => r.data),
  syncAutoJoin: (workspaceId: string, autoJoin = true) =>
    api
      .post<{ status: string; scanned: number; created: number; skipped: number }>(
        `/workspaces/${workspaceId}/calendar/sync?auto_join=${autoJoin}`
      )
      .then((r) => r.data),
};

// Meetings
export interface TestJoinResult {
  meeting_id: string;
  platform: string;
  joining: boolean;
  websocket: string;
  scheduled_at?: string;
  note?: string | null;
  message: string;
}

export const meetingApi = {
  list: (workspaceId: string) =>
    api.get<Meeting[]>(`/workspaces/${workspaceId}/meetings`).then((r) => r.data),
  /** Paste a link + "now"/ISO time → real bot attends. */
  testJoin: (
    workspaceId: string,
    data: { meeting_url: string; when: string; mode: "recorder" | "assistant"; title?: string }
  ) => api.post<TestJoinResult>(`/workspaces/${workspaceId}/meetings/test-join`, data).then((r) => r.data),
  stopAssistant: (workspaceId: string, meetingId: string) =>
    api.post(`/workspaces/${workspaceId}/meetings/${meetingId}/assistant/stop`).then((r) => r.data),
  get: (workspaceId: string, meetingId: string) =>
    api.get<Meeting>(`/workspaces/${workspaceId}/meetings/${meetingId}`).then((r) => r.data),
  create: (workspaceId: string, data: Partial<Meeting>) =>
    api.post<Meeting>(`/workspaces/${workspaceId}/meetings`, data).then((r) => r.data),
  update: (workspaceId: string, meetingId: string, data: Partial<Meeting>) =>
    api.patch<Meeting>(`/workspaces/${workspaceId}/meetings/${meetingId}`, data).then((r) => r.data),
  start: (workspaceId: string, meetingId: string) =>
    api.post<Meeting>(`/workspaces/${workspaceId}/meetings/${meetingId}/start`).then((r) => r.data),
  end: (workspaceId: string, meetingId: string) =>
    api.post<Meeting>(`/workspaces/${workspaceId}/meetings/${meetingId}/end`).then((r) => r.data),
  uploadContext: (workspaceId: string, meetingId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post(`/workspaces/${workspaceId}/meetings/${meetingId}/upload-context`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    }).then((r) => r.data);
  },
  getPrepBrief: (workspaceId: string, meetingId: string) =>
    api.get<PrepBrief>(`/workspaces/${workspaceId}/meetings/${meetingId}/prep-brief`).then((r) => r.data),
  generateQuestions: (workspaceId: string, meetingId: string) =>
    api.post<{ generated: number }>(`/workspaces/${workspaceId}/meetings/${meetingId}/generate-questions`).then((r) => r.data),
};

// Questions
export const questionApi = {
  list: (workspaceId: string, meetingId: string) =>
    api.get<Question[]>(`/workspaces/${workspaceId}/meetings/${meetingId}/questions`).then((r) => r.data),
  create: (workspaceId: string, meetingId: string, data: Partial<Question>) =>
    api.post<Question>(`/workspaces/${workspaceId}/meetings/${meetingId}/questions`, data).then((r) => r.data),
  update: (workspaceId: string, meetingId: string, questionId: string, data: Partial<Question>) =>
    api.patch<Question>(`/workspaces/${workspaceId}/meetings/${meetingId}/questions/${questionId}`, data).then((r) => r.data),
  delete: (workspaceId: string, meetingId: string, questionId: string) =>
    api.delete(`/workspaces/${workspaceId}/meetings/${meetingId}/questions/${questionId}`),
  bulkApproveProxy: (workspaceId: string, meetingId: string, questionIds: string[]) =>
    api.post(`/workspaces/${workspaceId}/meetings/${meetingId}/questions/bulk-approve`, questionIds).then((r) => r.data),
};

// Reports
export const reportApi = {
  list: (workspaceId: string, meetingId: string) =>
    api.get<Report[]>(`/workspaces/${workspaceId}/meetings/${meetingId}/reports`).then((r) => r.data),
  generate: (workspaceId: string, meetingId: string) =>
    api.post<Report>(`/workspaces/${workspaceId}/meetings/${meetingId}/reports/generate`).then((r) => r.data),
  sendSlack: (workspaceId: string, meetingId: string, reportId: string, channel: string) =>
    api.post(`/workspaces/${workspaceId}/meetings/${meetingId}/reports/${reportId}/send-slack?channel=${channel}`).then((r) => r.data),
};

// Knowledge
export const knowledgeApi = {
  query: (workspaceId: string, query: string, limit = 5) =>
    api.post<{ answer: string; sources: unknown[] }>(`/workspaces/${workspaceId}/knowledge/query`, { query, limit }).then((r) => r.data),
};

// Integrations
export const integrationApi = {
  list: (workspaceId: string) =>
    api.get<unknown[]>(`/workspaces/${workspaceId}/integrations`).then((r) => r.data),
  connect: (workspaceId: string, provider: string) =>
    api.post(`/workspaces/${workspaceId}/integrations/${provider}/connect`).then((r) => r.data),
  disconnect: (workspaceId: string, provider: string) =>
    api.delete(`/workspaces/${workspaceId}/integrations/${provider}/disconnect`).then((r) => r.data),
};

// Meeting Assistant agent
export const assistantApi = {
  start: (
    workspaceId: string,
    meetingId: string,
    data: { mode: "assistant" | "recorder"; meeting_url?: string; simulate?: boolean; assistant_name?: string }
  ) =>
    api.post<{ status: string; mode: string; message: string }>(
      `/workspaces/${workspaceId}/meetings/${meetingId}/assistant/start`,
      data
    ).then((r) => r.data),
  stop: (workspaceId: string, meetingId: string) =>
    api.post<{ status: string }>(`/workspaces/${workspaceId}/meetings/${meetingId}/assistant/stop`).then((r) => r.data),
};

// Live session / meeting bot
export const liveSessionApi = {
  joinMeeting: (
    workspaceId: string,
    meetingId: string,
    data: { meeting_url: string; simulate?: boolean }
  ) =>
    api.post<{ status: string; questions_queued: number; message: string }>(
      `/workspaces/${workspaceId}/meetings/${meetingId}/bot/join`,
      data
    ).then((r) => r.data),

  getBotStatus: (workspaceId: string, meetingId: string) =>
    api.get<import("./types").MeetingBot>(
      `/workspaces/${workspaceId}/meetings/${meetingId}/bot/status`
    ).then((r) => r.data),

  leaveMeeting: (workspaceId: string, meetingId: string) =>
    api.post<{ status: string }>(
      `/workspaces/${workspaceId}/meetings/${meetingId}/bot/leave`
    ).then((r) => r.data),

  transcribeAudio: (workspaceId: string, meetingId: string, audioFile: File) => {
    const form = new FormData();
    form.append("audio_file", audioFile);
    return api
      .post<{ transcript: string; chars: number; filename: string }>(
        `/workspaces/${workspaceId}/meetings/${meetingId}/transcribe-audio`,
        form,
        { headers: { "Content-Type": "multipart/form-data" } }
      )
      .then((r) => r.data);
  },

  // Real authenticated TTS: POST the text, get an MP3 blob back as an object URL.
  synthesizeSpeech: async (workspaceId: string, text: string): Promise<string> => {
    const res = await api.post(`/workspaces/${workspaceId}/tts`, { text, voice: "nova" }, {
      responseType: "blob",
    });
    return URL.createObjectURL(res.data as Blob);
  },
};

// ─── Speak Mode ──────────────────────────────────────────────────────────────
export interface SpeakPoint {
  id: string;
  text: string;
  stage: string;
  priority: "must" | "should" | "nice";
  order_index: number;
  status: "pending" | "covered" | "missed";
  covered_by_text?: string | null;
}
export interface SpeakResponse {
  id: string;
  speaker: string;
  text: string;
  kind: string;
  point_id: string | null;
}
export interface SpeakState {
  points: SpeakPoint[];
  responses: SpeakResponse[];
  progress: { total: number; covered: number; missed: number; pending: number; must_remaining: number };
}
export interface SpeakSummary {
  summary: string;
  covered: string[];
  missed: string[];
  action_items: { title: string; owner?: string | null }[];
  follow_ups: string[];
  responses: { speaker: string; text: string; kind: string }[];
  report_id?: string;
}

export const speakApi = {
  generate: (workspaceId: string, meetingId: string, text: string) =>
    api
      .post<SpeakState>(`/workspaces/${workspaceId}/meetings/${meetingId}/speak/points/generate`, { text })
      .then((r) => r.data),
  state: (workspaceId: string, meetingId: string) =>
    api.get<SpeakState>(`/workspaces/${workspaceId}/meetings/${meetingId}/speak/state`).then((r) => r.data),
  updatePoint: (
    workspaceId: string,
    meetingId: string,
    pointId: string,
    data: Partial<Pick<SpeakPoint, "text" | "stage" | "priority" | "status">>
  ) =>
    api
      .put<SpeakPoint>(`/workspaces/${workspaceId}/meetings/${meetingId}/speak/points/${pointId}`, data)
      .then((r) => r.data),
  finalize: (workspaceId: string, meetingId: string) =>
    api.post<SpeakSummary>(`/workspaces/${workspaceId}/meetings/${meetingId}/speak/finalize`).then((r) => r.data),
  share: (workspaceId: string, meetingId: string, reportId: string) =>
    api
      .post<{ share_token: string; url: string }>(
        `/workspaces/${workspaceId}/meetings/${meetingId}/reports/${reportId}/share`
      )
      .then((r) => r.data),
};
