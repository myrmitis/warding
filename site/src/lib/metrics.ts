import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

/**
 * Open metrics for the lineage section, computed at build from the parent
 * repository's git history so the page never renders a "0" placeholder. When
 * git is unavailable (a checkout without history) the last measured values
 * are used and dated as such.
 */
export interface Metrics {
  commits30d: number;
  testFiles: number;
  latestTag: string; // "" -> "no tagged release yet"
  measuredOn: string; // ISO date
  live: boolean;
}

const SNAPSHOT: Metrics = { commits30d: 37, testFiles: 3334, latestTag: "", measuredOn: "2026-09-26", live: false };

const REPO = resolve(process.cwd(), "..");

function git(args: string[]): string {
  return execFileSync("git", ["-C", REPO, ...args], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
}

export function collectMetrics(): Metrics {
  try {
    const commits = git(["rev-list", "--count", "--since=30.days", "HEAD"]);
    const tests = git([
      "ls-files", "test/test_*.py", "src/junction/**/test_*.py", "website/src/**/*.test.ts", "website/src/**/*.test.tsx",
    ]).split("\n").filter(Boolean).length;
    let latestTag = "";
    try { latestTag = git(["describe", "--tags", "--abbrev=0"]); } catch { latestTag = ""; }
    const commits30d = Number(commits);
    if (!Number.isFinite(commits30d) || tests === 0) return SNAPSHOT;
    return { commits30d, testFiles: tests, latestTag, measuredOn: new Date().toISOString().slice(0, 10), live: true };
  } catch {
    return SNAPSHOT;
  }
}
