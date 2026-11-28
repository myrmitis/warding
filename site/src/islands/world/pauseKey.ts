export const PAUSE_KEY = "warding.world.paused";

export function readOfficePaused(): boolean {
  try {
    return localStorage.getItem(PAUSE_KEY) === "1";
  } catch {
    return false;
  }
}
