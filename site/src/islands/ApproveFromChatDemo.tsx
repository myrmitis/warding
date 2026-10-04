import { useState } from "react";
import { Ban, Check, Clock, Hand } from "lucide-react";
import { track } from "../lib/analytics";

/**
 * The 03:05 micro-conversion (site-spec §2.5): a phone card with real buttons.
 * Approve edits the bubble to "Approved · 03:05"; Deny to "Denied · 03:05";
 * a third, dimmed pill names the dawn-expiring grant that is in development.
 * Nothing auto-approves. The world listens for `warding:approval`.
 */
type Outcome = "" | "approve" | "deny";

export default function ApproveFromChatDemo() {
  const [outcome, setOutcome] = useState<Outcome>("");
  const decide = (action: "approve" | "deny") => {
    setOutcome(action);
    track("approve_tap", { action });
    window.dispatchEvent(new CustomEvent("warding:approval", { detail: { action } }));
  };
  const reset = () => setOutcome("");

  return (
    <div className="phone approve-demo" role="group" aria-label="Telegram chat, simulated">
      <div className="phone-head">
        <span>Telegram · Claude Code</span>
        <span className="clock" style={{ fontSize: 12 }}>03:05</span>
      </div>
      <div className="bubble">
        <span className="status status-held"><Hand className="lucide" aria-hidden="true" /> Waiting on you</span>
        <p style={{ marginTop: 6 }}>
          <code>claude</code> wants to run <code>git push origin fix/auth-flake</code> in <code>~/app</code>
        </p>
      </div>
      <div className="approve-actions">
        {outcome === "" ? (
          <>
            <button type="button" className="pill pill-approve" onClick={() => decide("approve")}>
              <Check className="lucide" aria-hidden="true" /> Approve
            </button>
            <button type="button" className="pill pill-deny" onClick={() => decide("deny")}>
              <Ban className="lucide" aria-hidden="true" /> Deny
            </button>
            <span className="pill pill-dim" aria-disabled="true" title="Dawn-expiring grants are in development">
              <Clock className="lucide" aria-hidden="true" /> Allow until 07:00 · in development
            </span>
          </>
        ) : (
          <>
            <span className={`bubble bubble-you ${outcome === "approve" ? "status-approved" : "status-refused"}`}>
              <span className="status">
                {outcome === "approve" ? <Check className="lucide" aria-hidden="true" /> : <Ban className="lucide" aria-hidden="true" />}
                {outcome === "approve" ? "Approved · 03:05" : "Denied · 03:05"}
              </span>
            </span>
            <button type="button" className="btn btn-quiet" onClick={reset}>Try the other one</button>
          </>
        )}
      </div>
      <p className="sr-only" aria-live="polite">
        {outcome === "approve" ? "Approved at 03:05. The push runs; the decision is in the audit log." : outcome === "deny" ? "Denied at 03:05. The agent returns to its desk; the decision is in the audit log." : ""}
      </p>
      <p className="caption" style={{ marginTop: 10 }}>
        {outcome === "approve" && "The push runs. The decision is in the log, and the log is chained."}
        {outcome === "deny" && "The sprite shrugs and returns. The decision is in the log, and the log is chained."}
        {outcome === "" && "Your tap is real; the chat is simulated. Nothing here auto-approves."}
      </p>
    </div>
  );
}
