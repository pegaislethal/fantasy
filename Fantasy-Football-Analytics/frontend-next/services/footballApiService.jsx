import { apiGet } from "@/services/api";

export function getMatches() {
  return apiGet("/api/user/matches/");
}

export function getPlayers() {
  return apiGet("/api/players/");
}
