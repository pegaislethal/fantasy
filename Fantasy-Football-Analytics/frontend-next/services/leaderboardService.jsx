import { apiGet } from "@/services/api";

export function getLeaderboard() {
  return apiGet("/api/user/leaderboard/");
}

export function getDashboard() {
  return apiGet("/api/user/dashboard/");
}
