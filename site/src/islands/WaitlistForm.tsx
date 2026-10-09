import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { site } from "../data/site";
import { track } from "../lib/analytics";

/**
 * Email capture with the fallback chain of site-spec §10, rendered server-side
 * too so it degrades without JavaScript:
 *   1. validate client-side, inline text error
 *   2. waitlist.endpoint set   -> POST JSON; on failure fall through
 *   3. waitlist.mailto set     -> open a prefilled mailto and show the text
 *   4. waitlist.discussionUrl  -> link + prefilled text to paste
 *   5. nothing configured      -> one line: GitHub's Watch -> Custom -> Releases, no label, no input
 * Every path keeps the address in localStorage (try/catch) under
 * `warding.waitlist.<list>`; it is never sent anywhere else.
 */
interface Question { id: string; label: string }
interface Props { list: string; label: string; questions?: Question[]; compact?: boolean }

type Path = "endpoint" | "mailto" | "discussion" | "none";
const path: Path = site.waitlist.endpoint ? "endpoint" : site.waitlist.mailto ? "mailto" : site.waitlist.discussionUrl ? "discussion" : "none";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

function prefill(list: string, email: string, answers: Record<string, string>) {
  const lines = [`Waitlist: ${list}`, `Email: ${email}`, ...Object.entries(answers).map(([k, v]) => `${k}: ${v}`)];
  return lines.join("\n");
}

export default function WaitlistForm({ list, label, questions = [], compact = false }: Props) {
  const [email, setEmail] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [done, setDone] = useState<"" | Path>("");
  const [joined, setJoined] = useState("");
  const [copied, setCopied] = useState(false);
  const timer = useRef(0);
  const key = `warding.waitlist.${list}`;

  useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw) { const v = JSON.parse(raw) as { email: string; at: string }; setJoined(v.at); setEmail(v.email); }
    } catch { /* no storage */ }
    return () => window.clearTimeout(timer.current);
  }, [key]);

  const remember = (addr: string) => {
    try { localStorage.setItem(key, JSON.stringify({ email: addr, at: new Date().toISOString().slice(0, 10) })); } catch { /* fine */ }
  };

  const text = prefill(list, email, answers);

  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setCopied(true); timer.current = window.setTimeout(() => setCopied(false), 1800); } catch { /* selectable by hand */ }
  };

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const addr = email.trim();
    if (!EMAIL.test(addr)) { setError("That does not look like an email address. Check for a typo."); return; }
    setError("");
    remember(addr);
    if (path === "endpoint") {
      try {
        const res = await fetch(site.waitlist.endpoint, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: addr, list, answers }) });
        if (res.ok) { setDone("endpoint"); track("waitlist_submit", { list }); return; }
      } catch { /* fall through */ }
    }
    if (site.waitlist.mailto) {
      const href = `mailto:${site.waitlist.mailto}?subject=${encodeURIComponent(`Waitlist: ${list}`)}&body=${encodeURIComponent(text)}`;
      window.location.href = href;
      setDone("mailto"); track("waitlist_fallback", { path: "mailto" }); return;
    }
    if (site.waitlist.discussionUrl) { setDone("discussion"); track("waitlist_fallback", { path: "discussion" }); return; }
    setDone("none"); track("waitlist_fallback", { path: "none" });
  };

  // With nothing configured there is no field, so no label either: one line
  // pointing at GitHub's own release notifications instead of a dead capture.
  if (path === "none") return <ReleaseNoteLine />;

  const formAction = path === "endpoint" ? site.waitlist.endpoint : path === "mailto" ? `mailto:${site.waitlist.mailto}?subject=${encodeURIComponent(`Waitlist: ${list}`)}` : site.waitlist.discussionUrl;

  return (
    <div className={`waitlist ${compact ? "waitlist-compact" : ""}`}>
      {done === "" ? (
        <form method={path === "discussion" ? "get" : "post"} action={formAction} encType={path === "mailto" ? "text/plain" : undefined} onSubmit={submit} noValidate>
          <label className="ui" htmlFor={`wl-${list}`}>{label}</label>
          {joined && <p className="caption">You joined this list on {joined}. Send again if you like.</p>}
          <div className="waitlist-row">
            <input id={`wl-${list}`} name="email" type="email" inputMode="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" aria-describedby={error ? `wl-${list}-err` : undefined} aria-invalid={error ? true : undefined} />
            <input type="hidden" name="list" value={list} />
            <button type="submit" className="btn btn-primary">Join the list</button>
          </div>
          {questions.map((q) => (
            <label key={q.id} className="waitlist-q">
              <span className="caption">{q.label}</span>
              <input name={q.id} type="text" value={answers[q.id] ?? ""} onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} />
            </label>
          ))}
          {error && <p id={`wl-${list}-err`} className="waitlist-error" role="alert">{error}</p>}
          <p className="caption">Kept in your browser only until it is sent. We email only when there is something to say.</p>
        </form>
      ) : done === "endpoint" ? (
        <p aria-live="polite">You're on the {list} list. We email only when there is something to say.</p>
      ) : (
        <div aria-live="polite" className="waitlist-fallback">
          {done === "mailto" && <p>Your mail app opened with the details filled in. If it didn't, copy this:</p>}
          {done === "discussion" && (
            <p>We don't have a mailing list yet. Post a reply in <a href={site.waitlist.discussionUrl} rel="noopener">this GitHub Discussion</a> and we'll count you in:</p>
          )}
          {done === "none" && <ReleaseNoteLine />}
          {done !== "none" && (
            <div className="copybox">
              <pre><code>{text}</code></pre>
              <button type="button" className="btn btn-quiet" onClick={copy}>
                {copied ? <Check className="lucide" aria-hidden="true" /> : <Copy className="lucide" aria-hidden="true" />} {copied ? "Copied" : "Copy"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** The capture used while no waitlist backend exists: GitHub's own release notifications. */
export function ReleaseNoteLine() {
  return (
    <p className="caption release-note">
      Get the release note: <a href={`${site.githubRepo}/releases`} rel="noopener">Watch → Custom → Releases on GitHub</a>
    </p>
  );
}
