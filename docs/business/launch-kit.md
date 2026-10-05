# Warding — launch kit

**DRAFT for the founder to rewrite in their own words. Nothing here is for
posting as written.** Hacker News forbids generated or AI-edited text and
Reddit communities ban it; the founder writes and posts everything on every
third-party platform personally, from their own accounts. The Growth role keeps
this file current; the Honesty auditor checks every claim in it against the
[claims register](README.md) and the verification log.

Truth rules that bind every asset: every frame is recorded, never mocked; the
harness and the date are in frame; chat runs the one harness chosen in one
setting, and a subagent the harness router sends to another harness is
registered, not verified; only a harness with a dated row on `/verified` is
named as verified; the Claude adapter is the
ACP project's `claude-agent-acp`, fetched with `npx` on first run; buttons exist
on five channels (Slack, Discord, Telegram, Teams, Webex), WhatsApp approves by
typed reply, iMessage, WeChat, WeCom and Feishu are chat-only; no number that
was not measured; no owned phrase (control plane, command center, mission
control, orchestrate, autopilot, while you sleep, from anywhere, in your pocket,
AI teammate); no version string before a tag exists. Nothing launches before
gates G1–G10 are green; no Show HN before three recorded Claude Code nights.

## 1. Hero GIF storyboard (six beats, about 24 seconds, loops)

Capture: a real Mac mini, the Warding dashboard on the left and the phone's
Telegram on the right (screen-mirrored or captured), the harness and date chip
in frame throughout ("Claude Code · via `claude-agent-acp` · Mac mini · YYYY-MM-DD").
Source 2880×1800, exported at 1200×675, 12–15 fps, under 10 MB as a GIF plus an
MP4 twin. Captions large, bottom-left, readable on a phone. Cut from the G7
recordings only; a GIF cut from anything else trips kill criterion K7.

| Beat | Time | Dashboard (left) | Telegram (right) | Caption |
|---|---|---|---|---|
| 1 | 0–4 s | Agent Worlds Office at night. One sprite at a desk, session label `nightly-deps · claude`. The clock reads 02:14. | Lock screen, 02:14. | "02:14. The lamp's still on." |
| 2 | 4–8 s | The session shows the pending-approval state (the existing overlay until the hand-raised pose ships). | A bot message arrives: "claude wants to run `git push origin nightly-deps` in `~/app`", with Approve and Deny buttons. | "It asks before `git push`." |
| 3 | 8–11 s | The sprite sits back down; the approval event lands in the session. | Thumb taps Approve; the message updates to Approved. | "You say yes from Telegram." |
| 4 | 11–16 s | The agent tries `cat ~/.ssh/id_rsa`. The seal stamps: "Refused · keystone · 02:31:07 · `cat ~/.ssh/id_rsa` · sha256:…" and the audit line prints under it. | Nothing arrives. | "Some things never reach your phone. Refused at Warding's own gate: `~/.ssh` is on the deny list." |
| 5 | 16–20 s | Morning. The cron execution calendar shows the job as run at 06:00, with its artifact. (The Morning Report card replaces this beat once it ships.) | The job's completion message, only if the channel really sent one. | "07:00. Done, asked once, refused once. It's in the log, and the log is chained." |
| 6 | 20–24 s | End card: the Ward Seal, "Warding", and the install line that works. | — | "One agent, all night, on your own box." |

Notes: beat 5's summary message is shown only if it was really sent; otherwise
the beat shows the calendar alone. The end card carries no star count and no
version until a tag exists. The same six beats, as still frames, are the three
Product Hunt gallery images (beats 1, 3 and 4) at 1270×760.

## 2. Sixty-second video script

Founder's voice. Every line maps to a mechanism that ships today; the two
`[COMING]` lines are cut if their feature has not landed on the recording date.

| Time | Visual | Voice-over | On-screen text |
|---|---|---|---|
| 0:00–0:05 | Close-up of the pixel office at night, one sprite typing | "This is my late desk." | Warding |
| 0:05–0:14 | Pull back to the dashboard. The harness setting shows Claude Code selected; the runtime list scrolls (Cursor, Codex, Kimi, DeepSeek, Goose, Grok, OpenCode, Pi, Droid, kiro-cli). | "It runs the coding agent I already pay for, on my own machine. Claude Code today, through the ACP project's adapter. Chat runs the one I choose in one setting." | "Your agent. Your machine. Your login." |
| 0:14–0:24 | The Telegram approval from the GIF | "When it wants to do something risky, it asks me in Telegram. Slack, Discord, Teams and Webex get the same buttons; WhatsApp takes a typed yes." | "Ask first" |
| 0:24–0:34 | The refused `~/.ssh` read and the audit line | "Some things it's not allowed to do at all. `~/.ssh` and its own policy file are on a deny list that Warding's own gate enforces, inside the OS sandbox, and every decision lands in a hash-chained log." | "The policy it can't open" |
| 0:34–0:42 | The schedule template gallery; a job is created | "Schedules run on my box. No run cap from us; my model plan's limits still apply." | "On a schedule" |
| 0:42–0:49 | Memory and skills page, then the apps grid | "It keeps lessons across sessions and ships twenty-one apps and eighteen themes." | — |
| 0:49–0:55 | Title card | "Open source. The late desk is ours. Apache-2.0." | "Open source" |
| 0:55–1:00 | The install line | "One command. Link below." | the install line that works |

## 3. Show HN

The founder writes the post. What follows is the fact sheet and three title
shapes, not text to paste. HN's title limit is 80 characters; each candidate is
79 with the en dash. The title names only a harness with a dated night on
`/verified` (Claude Code after G7; never Codex, whose night is recorded after
Show HN). The link is the GitHub repository, not the site. Post on a Sunday
around 16:00 UTC when the founder can answer for eight hours; no other channel
that day.

Title candidates:

1. `Show HN: Warding – Claude Code overnight on your own box, approve from Telegram`
2. `Show HN: Warding – a self-hosted late desk for Claude Code, with chat approvals`
3. `Show HN: Warding – Claude Code overnight, under rules it cannot read or rewrite`

Body shape (the founder's words): what works, with the
limit in the same sentence; what does not work yet; the one command; the two
questions the founder wants feedback on (the policy model; which chat apps
people would use for approvals).

### Fact sheet the founder answers from

Every line is true on 2026-09-30; the Honesty auditor refreshes it before the
post.

- **Harnesses registered:** Cursor, Claude Code, Codex, Kimi, DeepSeek Harness,
  Goose, Grok, OpenCode, Pi, Droid, kiro-cli. Chat sessions run the one harness
  you choose in one setting; spawned subagents can be routed to another
  installed harness by the harness router (flat-rate quota before metered,
  task kind, cooldown after a usage limit or failed login), which picks a
  harness and never forwards provider traffic. Verified: only what has a dated
  row on `/verified` (today: Claude Code for chat); OpenCode and the router are
  registered · unverified. Gemini is not docked.
- **Claude Code:** launched under your own login through the official `claude`
  CLI and the ACP project's `claude-agent-acp` adapter, fetched with `npx` on
  first run. Anthropic's terms govern; for shared or production automation use an
  API key. Never say "ToS-safe". Anthropic's separate metering of unattended
  agent use is paused, not cancelled, so "the plan you already pay for" holds
  until they change it.
- **Channels:** ten. Approve buttons on Slack, Discord, Telegram, Teams, Webex;
  typed approvals on WhatsApp; iMessage, WeChat, WeCom and Feishu are chat-only.
- **What is different:** harnesses beyond kiro-cli (Cursor, Kimi, DeepSeek
  Harness, Grok and Droid among them), kiro-cli optional and last, no vendor
  account in the door, no vendor-owned endpoint in the default build. Not yet:
  KAS, signed installers, a wheel, Docker, and MCP tools on the non-Kiro
  harnesses.
- **Security, with the mechanism:** the policy files under the data home are on
  a sensitive-path deny list enforced at Warding's own PreToolUse gate, so the
  agent can neither read nor write them; built-in deny rules refuse destructive
  commands and reads of `~/.ssh` and `~/.aws`; the process runs in an OS sandbox
  (Seatbelt on macOS, including macOS 26; user namespaces on Linux, which need
  an opt-in step on Ubuntu 23.10 and later and in containers; opt-in on
  Windows); credentials are redacted from tool output; every tool decision is
  appended to an HMAC-chained audit log. Documented fail-open path: a tool the
  harness pre-authorised can skip the PreToolUse gate; computer-use refusals run
  in band. Unaudited by a third party; the bypass script and bounty are
  `[COMING]`.
- **Cron, subagents, `ask_question` from chat:** on kiro-cli only today. On
  other harnesses cron and subagents work from the dashboard and CLI, and the
  agent has no `ask_question` tool.
- **Single owner.** No multi-user, no teams, no hosted service.
- **RAM:** idle gateway 452 MB, measured; under load unmeasured until the
  nights are recorded.
- **Install:** clone plus Node build today; the wheel and one-line install are
  gate G2. Install time on a clean box: unmeasured until then.
- **Telemetry:** the default build contacts no server of ours; the embedding
  model is fetched from a third-party CDN on first use; an opt-in beacon to an
  owned endpoint is gate G6.
- **Windows:** native, with the sandbox opt-in.
- **Why Python plus a React SPA:** the gateway is Python and the dashboard is a
  React SPA; we did not rewrite either.
- **Counts:** 21 built-in apps, 18 themes, 12 dashboard languages. No star,
  user or customer count.

## 4. Product Hunt

Launch on a Saturday about a week after Show HN, at 00:01 PT. No waitlist on
the page (Product Hunt excludes waitlisted products). Never "please upvote";
"tell us what's missing" is the ask. Three gallery images from the GIF's beats
at 1270×760, plus the 60-second video.

- **Name:** Warding
- **Tagline (59 of 60 characters):** `Your coding agent, all night, on your own box, asking first`
- **Description (257 of 260 characters):** `Runs the coding agent you already pay for on your own machine, on a schedule: Claude Code, Codex, Goose, Cursor and more, one for chat. Reports into Telegram or Slack and asks first before anything risky, under a policy it can't read or rewrite. Apache-2.0.`
- **First comment (founder rewrites; under 800 characters):** "Hi, I'm
  [name]. I wanted my coding agent to keep working on my own box after I closed
  the laptop, and to ask me before anything risky, without tying the setup to
  one vendor's cloud. Warding is open source (Apache-2.0). It has a registry
  that docks Claude Code, Codex, Goose, Cursor and more, with kiro-cli
  optional; chat runs the one you choose. Approvals arrive as buttons in Telegram, Slack, Discord, Teams and
  Webex; a deny list the agent can't read decides what never gets asked. Free,
  self-hosted, one command to install. What would you schedule first?"

## 5. Five tweets (links in the first reply; the founder rewrites)

1. (video) "02:14. Claude Code is working on my Mac mini. It wants to push a
   branch, so it asks me in Telegram. I tap Approve. The read of ~/.ssh it
   tried at 02:31 never asked; the deny list at Warding's own gate said no.
   Open source, self-hosted."
2. "Warding docks Claude Code, Codex, Goose, Cursor and seven more; chat runs
   the one you choose. Open source (Apache-2.0), self-hosted, free."
3. "Things my agent is not allowed to do, whatever I approve in chat: read
   ~/.ssh or ~/.aws, open its own policy file, run the built-in destructive
   commands. The policy path is on a deny list enforced at Warding's own gate,
   inside the OS sandbox, and every decision lands in a hash-chained log."
4. "Build log: install on a clean box went from [measured] to [measured], and a
   first run with Claude Code no longer needs a manual adapter step. Launch is
   Sunday." (Only with the two measured numbers filled in and a real GIF.)
5. "What should a coding agent be allowed to do at 03:00? Mine can run tests
   and open PRs. It must ask before migrations and pushes. Never: secrets, its
   own rules. Where do you draw the line?" (A question; no product claim.)

## 6. Reddit (one draft per community; the founder adapts and posts)

Rules below are secondhand: Reddit returned 403 to the research session, so
the founder reads each community's sidebar and wiki before posting. General
norm: the 1-in-10 rule, affiliation disclosed in the first lines, one community
per 24–48 hours, never the same body twice, stay in the thread for three hours.

**r/ClaudeCode** (flair Showcase or Resource; promotions must state what the
tool does, who benefits, cost, and the poster's relationship)
> Title: I leave Claude Code running on a Mac mini overnight and approve risky
> commands from Telegram: the setup, and what the policy refuses
> Disclosure: I'm the developer of Warding, the free, open-source (Apache-2.0)
> tool this uses. Nothing here needs a paid tier.
> What it does: runs Claude Code on your own box under your own login, through
> the ACP project's `claude-agent-acp` adapter; scheduled jobs; tool approvals
> as Telegram buttons; a deny list the agent can't read or edit.
> Cost: free; your normal Claude plan usage applies, and Anthropic's terms
> govern unattended use.
> Setup: [the real steps]. What went wrong: [honest]. Limits: chat runs one
> harness, chosen in one setting; sending subagents to another harness is not
> verified yet; single owner; cron from chat needs kiro-cli today.
> Where would you draw the approve/deny line?

**r/ClaudeAI** (flair Built with Claude; the four required parts: what you
built, how, screenshots or demo, at least one prompt you used)
> What I built: ... How I built it: [the real steps]; Claude Code wrote [measured share] of the registry layer.
> Screenshots: [the GIF, harness and date in frame]. A prompt I used: "Every
> night at 02:00, run the test suite, open a PR for any flaky test you can fix,
> and ask me in Telegram before touching migrations."

**r/selfhosted** (self-promotion tolerated but policed; lesson framing; weekend
morning; an established account)
> Title: Running a coding agent on a home server under a policy it can't edit:
> what worked and what didn't
> Body: the hardware and the measured RAM; why self-host (repos stay home; no
> run cap from us, plan limits still apply); the channel setup; what the
> sandbox refuses and where it needs an opt-in step; the failures. Warding is
> mentioned once with the disclosure line, the license, single-owner status,
> and the telemetry statement (only what is true after G6).

**r/opensource** (rules not retrievable; read them first)
> Title: Lessons from shipping an Apache-2.0 agent gateway: licensing,
> trademarks, removing vendor endpoints
> A genuine how-to; Warding named once.

**r/SideProject** (explicit yes to promotion)
> The founder story with the GIF: what the first month taught.

**r/ChatGPTCoding** (weekly self-promotion thread only, if it still exists)
> Two or three lines in the thread, framed around Codex, only once Codex has a
> verified row.

**r/LocalLLaMA:** do not post unless a local-model harness path is verified
end to end.

## 7. Newsletter pitch (five lines; the founder sends, one at a time)

> Subject: Warding (0.x, Apache-2.0): keep Claude Code working on your own box,
> approve from chat
> Hi. Warding docks Claude Code,
> Codex, Goose, Cursor and more, one chosen for chat; it runs scheduled jobs on your
> own machine and routes approvals to Telegram or Slack under a policy the agent
> can't read or edit. Pre-1.0; one-line install; docs at [site]; Show HN thread
> at [link]. Happy to answer questions. [name]

Targets and their rules: Console.dev (email; pre-1.0 only; no sponsored
reviews), TLDR (submissions address; pitch once, after HN, with a real number),
Changelog News (submit form; no commercial products, so the repo, not the
paid tier), Self-Host Weekly (submit form in each
issue), ruanyf/weekly (a GitHub issue in Chinese, written by a native speaker).

## 8. Awesome lists, directories and the ACP Clients page

The founder submits by hand, one at a time. An agent drafts the one-line
description and checks the criteria. Never an agent submission.

| Venue | Criteria to check | Eligible when | Checklist |
|---|---|---|---|
| awesome-claude-code | Web issue form only; human-created recommendations only; repository at least 14 days old with activity or 100 or more stars; one resource at a time; descriptions are not a sales pitch; no emoji; no signup or payment requirement | After G1 is re-verified on a clean Mac | One-line description ready; repo link; no pitch words; founder fills the form personally |
| awesome-agent-orchestrators | Open-source repository; at least 5 stars and signs of life; one entry per PR titled `Add Warding to <Section>`; one line saying what it does and which agents it supports; awesome-lint passes | At 5 or more stars, after a tagged release | Section chosen (Autonomous Task Runners or Personal Assistants); the one line names the harnesses that have verified rows; lint run locally |
| ACP Clients page (`docs/get-started/clients.mdx` in the ACP repository, Messaging section) | No written criteria; matches the existing entry style | After G1 | Diff prepared by an agent; the founder opens the PR from their own account; entry names the adapter it uses |
| awesome-selfhosted | First released more than four months ago; machine or LLM-generated contributions banned | Not before four months after the first tagged release | Do not submit in the 90-day plan |
| AlternativeTo | Rules page not retrievable | After a tagged release | Listed as an alternative to OpenClaw and Claude Code remote control; the founder submits |
| Other awesome lists (ai agents, ai devtools, ai coding tools, awesome-acp) | Criteria unverified | After a tagged release | The founder checks each list's contributing file first |
| ACP Registry | Agents only; a client cannot be listed | Never | Consume the registry instead |
| Paid directories | Payment required | Never | Skip |
