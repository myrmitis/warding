/**
 * Cookieless analytics events (site-spec §12). No-ops unless the page injected
 * a provider script (BaseLayout does so only when `site.analytics.provider` is
 * set). Never the email, never anything the provider does not strip.
 */
export type EventName =
  | "install_copy" | "approve_tap" | "github_click" | "waitlist_submit" | "waitlist_fallback"
  | "supporter_click" | "setup_click" | "pilot_call_click" | "wallpaper_save" | "pause_toggle";

declare global {
  interface Window {
    plausible?: (event: string, opts?: { props?: Record<string, string> }) => void;
    umami?: { track: (event: string, data?: Record<string, string>) => void };
  }
}

export function track(event: EventName, props: Record<string, string> = {}) {
  try {
    if (typeof window === "undefined") return;
    if (window.plausible) window.plausible(event, { props });
    else if (window.umami) window.umami.track(event, props);
  } catch {
    /* analytics must never break the page */
  }
}
