import { apiGet, apiPost } from "@/services/api";

export function getMyTeam() {
  return apiGet("/api/user/team/");
}

export function updateTeam(payload) {
  return apiPost("/api/user/team/", payload);
}

export function createNewSquad(formation = "4-4-2") {
  return apiPost("/api/user/team/", { formation, players: [] });
}

export default { getMyTeam, updateTeam, createNewSquad };
