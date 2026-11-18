import axios from "axios";

// Relative path — works unchanged in both local dev (Vite's dev-server proxy
// forwards /api to :8000) and on Vercel (vercel.json rewrites /api to the
// same-origin api/ service).
const baseURL = import.meta.env.VITE_API_BASE_URL || "/api";
export const api = axios.create({ baseURL });

const get = (url, params) => api.get(url, { params }).then((r) => r.data);

export const getOverview = () => get("/overview");
export const getChannels = () => get("/channels");
export const getChannel = (key) => get(`/channels/${key}`);
export const patchChannel = (key, body) => api.patch(`/channels/${key}`, body).then((r) => r.data);
export const getRuns = (params) => get("/runs", params);
export const getVideos = (params) => get("/videos", params);
export const getStories = (params) => get("/stories", params);
export const getLibrary = () => get("/library");
export const getActions = () => get("/actions");
export const getSystem = () => get("/system");
export const getInsights = (key) => get(`/insights/${key}`);
export const triggerRun = (key, dryRun = false) =>
  api.post(`/runs/trigger/${key}`, null, { params: { dry_run: dryRun } }).then((r) => r.data);
export const syncStats = () => api.post("/stats/sync").then((r) => r.data);

export const errMsg = (e) => e?.response?.data?.detail || e?.message || "Something went wrong";
