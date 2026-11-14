import axios from "axios";

export const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL}/api` });

const auth = (token) => ({ headers: { Authorization: `Bearer ${token}` } });

export const fetchNonce = (address) => api.get("/auth/nonce", { params: { address } }).then((r) => r.data.nonce);
export const verifyWallet = (message, signature) => api.post("/auth/verify", { message, signature }).then((r) => r.data);
export const fetchState = (token) => api.get("/game/state", auth(token)).then((r) => r.data);
export const fetchLeaderboard = (token) => api.get("/game/leaderboard", auth(token)).then((r) => r.data);
export const gameAction = (token, action, level) => api.post(`/game/${action}`, level ? { level } : {}, auth(token)).then((r) => r.data);

export const errorText = (err) => err?.response?.data?.detail || err?.shortMessage || err?.message || "Something went wrong";
