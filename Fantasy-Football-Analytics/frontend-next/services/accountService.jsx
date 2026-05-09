import { apiPatch } from "@/services/api";

export function updateProfile(payload) {
  return apiPatch("/api/user/profile/update/", payload);
}

export default { updateProfile };
