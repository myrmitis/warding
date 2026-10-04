import { useEffect, useId, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { site } from "../data/site";
import { GITHUB_MARK_PATH } from "../lib/github-mark";
import { track } from "../lib/analytics";

/**
 * The install block (site-spec §2.1). Until a package is published
 * (`site.installOneLiner === ""`) there is one way in, so the block shows the
 * three-line source quickstart with no pipx/uv/npm tabs to click into a "not
 * published yet" note, and the CTA reads "Copy the quickstart". The version
 * chip renders only when a tagged release exists (`version` is the tag); an
 * untagged pyproject version is never shown.
 */
type Tab = "pipx" | "uv" | "npm" | "source";
const TABS: Tab[] = ["pipx", "uv", "npm", "source"];

const QUICKSTART = [
  `git clone ${site.githubRepo}.git && cd junction`,
  "bash minimal_install.sh",
  `${site.cli} setup && ${site.cli} up`,
];

const ONE_LINER: Record<Exclude<Tab, "source">, string> = {
  pipx: `pipx install ${site.installOneLiner}`,
  uv: `uv tool install ${site.installOneLiner}`,
  npm: `npm i -g ${site.installOneLiner}`,
};

interface Props {
  /** The latest release tag; "" (no tagged release yet) hides the version chip. */
  version?: string;
  /** Render the "Star on GitHub" outline button next to Copy. */
  star?: boolean;
  /** The block's fragment id; "" omits it where the page already has its own #install. */
  anchor?: string;
}

export default function InstallTabs({ version = "", star = false, anchor = "install" }: Props) {
  const published = site.installOneLiner !== "";
  const [tab, setTab] = useState<Tab>(published ? "pipx" : "source");
  const [copied, setCopied] = useState(false);
  const timer = useRef(0);
  const id = useId();

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const lines = published && tab !== "source" ? [ONE_LINER[tab]] : QUICKSTART;
  const copy = async () => {
    const text = lines.join("\n");
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch { /* the block is still selectable by hand */ }
      ta.remove();
    }
    setCopied(true);
    track("install_copy", { tab });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(false), 1800);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (!published) return;
    const i = TABS.indexOf(tab);
    if (e.key === "ArrowRight") { e.preventDefault(); setTab(TABS[(i + 1) % TABS.length]); }
    if (e.key === "ArrowLeft") { e.preventDefault(); setTab(TABS[(i - 1 + TABS.length) % TABS.length]); }
  };

  return (
    <div className="install" id={anchor || undefined}>
      <div className="install-top">
        {published ? (
        <div role="tablist" aria-label="Install method" className="tabs" onKeyDown={onKey}>
          {TABS.map((t) => (
            <button
              key={t}
              role="tab"
              type="button"
              id={`${id}-tab-${t}`}
              aria-selected={tab === t}
              aria-controls={`${id}-panel`}
              tabIndex={tab === t ? 0 : -1}
              className={`tab ${tab === t ? "on" : ""}`}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>
        ) : (
          <p className="ui install-label">From source</p>
        )}
        {version && <span className="chip">{version}</span>}
      </div>
      <div role={published ? "tabpanel" : undefined} id={`${id}-panel`} aria-labelledby={published ? `${id}-tab-${tab}` : undefined} className="panel">
        {!published && tab !== "source" && (
          <p className="caption panel-note">
            <code>{tab === "npm" ? "npm i -g" : tab === "uv" ? "uv tool install" : "pipx install"} {site.cli}</code> is not published yet. From source, today:
          </p>
        )}
        <pre className="install-pre" tabIndex={0} role="region" aria-label="Install commands"><code>{lines.map((l, i) => (
          <span className="line" key={i}><span className="prompt" aria-hidden="true">$ </span>{l}{"\n"}</span>
        ))}</code></pre>
        <p className="caption">
          Needs <code>claude</code>, <code>codex</code>, <code>goose</code> or <code>kiro-cli</code> on your PATH, Python 3.10+ and Node 22+. <code>setup</code> finds your agent; <code>up</code> opens the dashboard in your browser.
        </p>
        <p className="caption" data-alias><code>{site.cliAlias}</code> also works.</p>
      </div>
      <div className="install-actions">
        <button type="button" className="btn btn-primary" onClick={copy} aria-live="off">
          {copied ? <Check className="lucide" aria-hidden="true" /> : <Copy className="lucide" aria-hidden="true" />}
          {published && tab !== "source" ? "Copy the install command" : "Copy the quickstart"}
        </button>
        {star && (
          <a className="btn btn-outline" href={site.githubRepo} rel="noopener" onClick={() => track("github_click")}>
            <svg className="gh-mark" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false"><path fill="currentColor" d={GITHUB_MARK_PATH} /></svg>
            Star on GitHub
          </a>
        )}
        <span className="sr-only" aria-live="polite">{copied ? "Copied" : ""}</span>
        <span className="caption copied" aria-hidden="true">{copied ? "Copied" : ""}</span>
      </div>
    </div>
  );
}
