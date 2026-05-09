import { apiGet, apiPost } from "@/services/api";

export function submitTransfer(payload) {
  /**
   * payload: { mode: 'buy'|'sell'|'swap', outName, inName, playerIn }
   */
  return apiPost("/api/user/transfers/submit/", payload);
}

export function getTransferMarket() {
  return apiGet("/api/user/transfers/market/");
}
