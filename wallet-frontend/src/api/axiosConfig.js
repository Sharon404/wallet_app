import axios from "axios";

// Create a configured axios instance
const axiosInstance = axios.create({
  baseURL: "http://127.0.0.1:8000/api/", // Django backend base URL
  headers: {
    "Content-Type": "application/json",
  },
});

// Optional: attach token if user is logged in
axiosInstance.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default axiosInstance;
