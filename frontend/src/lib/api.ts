import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
  headers: { "Content-Type": "application/json" },
  timeout: 120_000,
});

const TOKEN_KEY = "pairflow_token";

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && !err.config?.url?.includes("/auth/login")) {
      localStorage.removeItem(TOKEN_KEY);
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export type Member = {
  id: number;
  name: string;
  matrix_user_id: string | null;
  role: "DEVELOPER" | "QA";
  active: boolean;
  lead_order: number;
  config_gap: boolean;
};

export type Pair = {
  member_a: string;
  member_b: string | null;
  member_c?: string | null;
  pair_type: "DEV" | "QA" | "SOLO";
};

export type RoundPreview = {
  round_date: string;
  combo_index: number;
  combo_label: string;
  pairs: Pair[];
  team_lead: string | null;
  rendered_text: string;
};

export type RoomMessage = {
  id: number | string;
  kind: string;
  label: string;
  text: string;
  sent_at: string | null;
  sender?: string | null;
  is_bot?: boolean;
  event_id?: string | null;
};

export type AttendanceRow = {
  member_id: number;
  name: string;
  completed: boolean;
  on_time: boolean;
  outcome: string;
  task?: string | null;
  pair_context?: string | null;
  suggestion_summary?: string | null;
  power_score: number;
  sent_at?: string | null;
  has_suggestion?: boolean;
  ai_reason?: string | null;
};

export type SuggestionRank = {
  rank: number;
  name: string;
  power_score: number;
  reason: string;
  task?: string | null;
  pair_context?: string | null;
};

export type TodayAnalysis = {
  date: string;
  analyzed_at: string;
  source: string;
  summary: string;
  attendance: AttendanceRow[];
  suggestion_ranking: SuggestionRank[];
  stats: {
    total: number;
    completed: number;
    on_time: number;
    missed: number;
    with_suggestions: number;
  };
};

export type PerformanceScope = "today" | "week" | "month";

export type PerformanceRow = AttendanceRow & {
  eligible_days?: number;
  completed_days?: number;
  on_time_days?: number;
  clean_days?: number;
  completion_rate?: number;
  on_time_rate?: number;
  clean_rate?: number;
  current_streak?: number;
  suggestions_count?: number;
};

export type PerformanceView = {
  scope: PerformanceScope;
  period_label: string;
  period_start: string | null;
  period_end: string | null;
  summary: string;
  attendance: PerformanceRow[];
  stats: TodayAnalysis["stats"] & {
    eligible?: number;
    team_completion_rate?: number;
    team_on_time_rate?: number;
  };
};

export type BotStatus = {
  state: string;
  element_configured: boolean;
  element_connected: boolean;
  element_joined: boolean;
  e2ee_store_ready: boolean;
  database_connected: boolean;
  active_members: number;
  config_gaps: number;
  last_send_at: string | null;
  next_send_at: string | null;
  homeserver: string | null;
  room_id: string | null;
  room_label: string | null;
  room_name: string | null;
  task_room_id?: string | null;
  task_room_label?: string | null;
  task_room_name?: string | null;
  task_room_joined?: boolean | null;
  element_error: string | null;
  alerts: string[];
};

export type DashboardFeed = {
  today_messages: RoomMessage[];
  task_messages: RoomMessage[];
  task_month_start?: string;
  task_month_end?: string;
  task_week_start?: string;
  task_week_end?: string;
  analysis: TodayAnalysis | null;
  feed_cached?: boolean;
  feed_refreshing?: boolean;
  timestamp: string;
};

export type BotStatusWithFeed = BotStatus & {
  today_messages?: RoomMessage[];
  task_messages?: RoomMessage[];
  analysis?: TodayAnalysis | null;
};

export type RoomStatus = {
  configured: boolean;
  connected: boolean;
  joined: boolean;
  e2ee_store_ready: boolean;
  homeserver: string | null;
  room_label: string | null;
  room_name: string | null;
  today_messages: RoomMessage[];
  feed_refreshing?: boolean;
  error: string | null;
};

export type OpenRouterModel = {
  id: string;
  name: string;
  description: string | null;
  context_length: number | null;
  free: boolean;
};

export const login = (username: string, password: string) =>
  api
    .post<{ access_token: string }>("/auth/login", { username, password }, { timeout: 15_000 })
    .then((r) => r.data);

export const getMe = () =>
  api.get<{ username: string }>("/auth/me").then((r) => r.data);

export const getStatus = () =>
  api.get<BotStatus>("/dashboard/status", { timeout: 30_000 }).then((r) => r.data);

export const getFeed = (force = false) =>
  api
    .get<DashboardFeed>("/dashboard/feed", {
      params: force ? { force: true } : undefined,
      timeout: 60_000,
    })
    .then((r) => r.data);
export const getToday = () =>
  api.get<RoundPreview>("/dashboard/today", { timeout: 30_000 }).then((r) => r.data);
export const runAnalysis = () =>
  api.post<TodayAnalysis>("/analysis/run", undefined, { timeout: 180_000 }).then((r) => r.data);

export const getPerformance = (scope: PerformanceScope = "today") =>
  api
    .get<PerformanceView>("/analysis/performance", { params: { scope }, timeout: 30_000 })
    .then((r) => r.data);
export const getMembers = () =>
  api.get<Member[]>("/team/members", { timeout: 30_000 }).then((r) => r.data);
export const getLeadPreview = () =>
  api.get<{ next_leads: string[] }>("/team/lead-preview").then((r) => r.data);
export const getHistory = () => api.get("/rounds/history").then((r) => r.data);
export const getSettings = () => api.get("/settings").then((r) => r.data);
export const getRoomStatus = () =>
  api.get<RoomStatus>("/room/status", { timeout: 15_000 }).then((r) => r.data);

export type SendResult = {
  ok: boolean;
  kind: string;
  message?: string;
  error?: string;
  event_id?: string;
  text?: string;
};

export type ReportPreview = {
  caption: string;
  period_label: string;
  width: number;
  height: number;
  image_base64: string;
  member_count: number;
};

export const getRoomPreview = () =>
  api.get<RoundPreview>("/room/preview").then((r) => r.data);

export const getReportPreview = () =>
  api.get<ReportPreview>("/room/report-preview", { timeout: 180_000 }).then((r) => r.data);

export const sendPairs = () =>
  api.post<SendResult>("/room/send-pairs").then((r) => r.data);

export const sendReport = () =>
  api.post<SendResult>("/room/send-report", undefined, { timeout: 180_000 }).then((r) => r.data);

export type SavedReport = {
  id: number;
  period_type: "weekly" | "monthly";
  period_start: string;
  period_end: string;
  period_label: string;
  metrics: Record<string, unknown>;
  narrative: string | null;
  narrative_source: string | null;
  llm_provider: string | null;
  llm_model: string | null;
  ai_analysis: {
    executive_summary?: string;
    team_highlights?: string[];
    areas_to_improve?: string[];
    member_notes?: { name: string; assessment: string; standout?: boolean }[];
    top_suggestions?: { rank: number; member: string; summary: string; why_powerful?: string }[];
    recommendations?: string[];
    narrative_short?: string;
  };
  status: string;
  generated_at: string | null;
  ingestion_live: boolean;
  llm_error?: string | null;
};

export const getReports = () =>
  api.get<SavedReport[]>("/reports").then((r) => r.data);

export const getReport = (id: number) =>
  api.get<SavedReport>(`/reports/${id}`).then((r) => r.data);

export const generateReport = (period_type: "weekly" | "monthly") =>
  api
    .post<SavedReport>("/reports/generate", { period_type }, { timeout: 180_000 })
    .then((r) => r.data);

export const fetchOpenRouterModels = (params: {
  api_key?: string;
  free_only?: boolean;
  search?: string;
}) =>
  api
    .post<{ models: OpenRouterModel[]; total: number; error: string | null }>(
      "/settings/openrouter/models",
      params
    )
    .then((r) => r.data);

export const updateSettings = (key: string, value: Record<string, unknown>) =>
  api.put(`/settings/${key}`, value).then((r) => r.data);
