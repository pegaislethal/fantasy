import { apiPatch, apiPost } from "@/services/api";

export function updateProfile(payload) {
  return apiPatch("/api/user/profile/update/", payload);
}

export function changePassword(payload) {
  return apiPost("/api/user/password/change/", payload);
}

const accountService = { updateProfile, changePassword };

export default accountService;
