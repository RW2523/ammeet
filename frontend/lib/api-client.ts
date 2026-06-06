import { api } from "./api";
import type { ActionItem, Meeting, Person, PrepBrief, Question, Report, User, Workspace } from "./types";

// Auth
export const authApi = {
  register: (data: { email: string; password: string; full_name: string }) =>
    api.post<User>("/auth/register", data).then((r) => r.data),
  login: (data: { email: string; password: string; totp_code?: string }) =>
    api.post<{ access_token: string; refresh_token: string }>("/auth/login", data).then((r) => r.data),
  me: () => api.get<User>("/auth/me").then((r) => r.data),
  setupMfa: () => api.post<{ secret: string; uri: string }>("/auth/mfa/setup").then((r) => r.data),
  verifyMfa: (code: string) => api.post("/auth/mfa/verify", { code }).then((r) => r.data),
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

// Meetings
export const meetingApi = {
  list: (workspaceId: string) =>
    api.get<Meeting[]>(`/workspaces/${workspaceId}/meetings`).then((r) => r.data),
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
