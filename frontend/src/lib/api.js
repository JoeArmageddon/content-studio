import axios from "axios";

// Points at the FastAPI backend — override with VITE_API_BASE_URL if it's
// not running on localhost:8000 (see backend/README quick start).
const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

export const api = axios.create({ baseURL });

export const getChannels = () => api.get("/channels").then((r) => r.data);
export const getChannel = (key) => api.get(`/channels/${key}`).then((r) => r.data);
export const getRuns = (channelKey, limit = 50) =>
  api.get("/runs", { params: { channel_key: channelKey, limit } }).then((r) => r.data);
export const getVideos = (channelKey, limit = 50) =>
  api.get("/videos", { params: { channel_key: channelKey, limit } }).then((r) => r.data);
export const getInsights = (channelKey) => api.get(`/insights/${channelKey}`).then((r) => r.data);
export const triggerRun = (channelKey) => api.post(`/runs/trigger/${channelKey}`).then((r) => r.data);
