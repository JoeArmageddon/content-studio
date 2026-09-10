import axios from "axios";

// Relative path — works unchanged in both local dev (Vite's dev-server
// proxy in vite.config.js forwards /api to the backend on :8000) and
// production on Vercel (vercel.json's rewrite sends /api to the same-origin
// api/ service) — one code path, no env var needed either way. Override
// with VITE_API_BASE_URL only if the backend genuinely lives on a
// different origin than whatever's serving this frontend.
const baseURL = import.meta.env.VITE_API_BASE_URL || "/api";

export const api = axios.create({ baseURL });

export const getChannels = () => api.get("/channels").then((r) => r.data);
export const getChannel = (key) => api.get(`/channels/${key}`).then((r) => r.data);
export const getRuns = (channelKey, limit = 50) =>
  api.get("/runs", { params: { channel_key: channelKey, limit } }).then((r) => r.data);
export const getVideos = (channelKey, limit = 50) =>
  api.get("/videos", { params: { channel_key: channelKey, limit } }).then((r) => r.data);
export const getInsights = (channelKey) => api.get(`/insights/${channelKey}`).then((r) => r.data);
export const triggerRun = (channelKey) => api.post(`/runs/trigger/${channelKey}`).then((r) => r.data);
