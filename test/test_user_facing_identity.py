"""User-facing identity is Warding, and the README obeys the forbidden-claims list.

The product name, the CLI name and the tagline are pinned
here because a rename that misses one surface ships a stale name silently.
The README assertions mirror the site's forbidden-claims list: a phrase
another company headlines with, a claim that is not true on this tree, or a
number nobody measured must not appear. The retired
identity is asserted absent from every public surface as well.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from warding import cli_help
from warding.constants import CLI_BIN, PRODUCT_NAME, SITE_URL, TAGLINE

_REPO_ROOT = Path(__file__).resolve().parents[1]

# The retired identity's tokens, assembled from fragments so this file does not
# itself carry the spellings it asserts are absent.
_RETIRED_PROSE = "Kiro" + " Crew"
_RETIRED_CONCAT = "Kiro" + "Crew"
_RETIRED_CLI = "kiro" + "crew"
_RETIRED_ORG = "kiro" + "dotdev"
_RETIRED_SLUG = f"{_RETIRED_ORG}/{_RETIRED_CONCAT}"
_RETIRED_DOWNLOAD_HOST = "download." + "crew" + ".kiro.dev"

# Phrases the README must never carry, case-insensitive. Owned by other
# companies as headlines, or untrue on this tree.
_FORBIDDEN_README_PHRASES = (
    "where coding agents meet the models you want",
    "control plane",
    "command center",
    "orchestrat",
    "autopilot",
    "while you sleep",
    "from anywhere",
    "in your pocket",
    "ai teammate",
    "side by side",
    "side-by-side",
    "routes your models",
    "route your models",
    "model router",
    "cheaper tokens",
    "pip install warding",
    "pip install warding",
    "docker pull",
    "works out of the box",
    "nothing leaves your machine",
    "unbreakable",
    "zero-trust",
    "certified",
    "10x",
    "trusted by",
    "warding.computer",
    "harness plane",
    "model plane",
    "route spend",
)

# The seal's keyhole shaft, verbatim in every surface that draws the mark.
_SEAL_SHAFT_PATH = "M29 28h6v5h-6zM29 35.5h6v2h-6zM29 40h6v2h-6zM29 44.5h6v1.5h-6z"


def _readme() -> str:
    return (_REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_constants_are_warding() -> None:
    assert PRODUCT_NAME == "Warding"
    assert CLI_BIN == "warding"
    assert TAGLINE == "The lamp stays on. The rules stay shut."
    assert SITE_URL == "https://warding.dev"


def test_readme_leads_with_warding() -> None:
    readme = _readme()
    head = readme[:1500]
    assert "Warding" in head
    assert "Built on" not in head
    assert 'src="assets/banner.svg"' in readme
    assert "The lamp stays on. The rules stay shut." in readme
    # Chat runs the one harness chosen in one setting; the harness router may
    # send a spawned subagent elsewhere, and says it forwards no provider traffic.
    assert "your chat sessions run the one harness" in " ".join(readme.lower().split())
    assert "never forwards provider traffic" in " ".join(readme.lower().split())
    assert "one harness at a time" not in readme.lower()
    # The quickstart is the source install; the CLI is warding.
    assert "git clone https://github.com/myrmitis/warding.git" in readme
    assert "bash minimal_install.sh" in readme
    assert "warding setup" in readme
    assert "warding up" in readme
    assert "scripts/get-warding.sh" in readme
    assert "claude-agent-acp" in readme
    assert "fetched with `npx` on first run" in readme
    # Sections the page is built from.
    for heading in (
        "## Quickstart",
        "## What it does",
        "## The rules it can't open",
        "## What we don't claim",
        "## Agent Worlds",
        "## Pricing",
        "## Contributing",
        "## Security",
        "## License",
    ):
        assert heading in readme, heading
    assert "Daily Active Crews" not in readme
    assert "founding group" not in readme
    assert "Kiro sign-in" not in readme
    assert "github.com/0618.png" not in readme
    assert _RETIRED_PROSE not in readme
    assert _RETIRED_CONCAT not in readme
    assert _RETIRED_DOWNLOAD_HOST not in readme


def test_readme_obeys_the_forbidden_claims_list() -> None:
    lower = _readme().lower()
    for phrase in _FORBIDDEN_README_PHRASES:
        assert phrase not in lower, phrase
    # No star, user or download counts, and no badges for them.
    assert "img.shields.io/github/stars" not in lower
    assert "img.shields.io/github/downloads" not in lower
    assert re.search(r"\b\d[\d,.]*k?\+?\s+(stars|users|downloads)\b", lower) is None
    # The four articles carry their mechanism, and the audit stance is stated.
    assert "unaudited by a third party" in lower
    assert "pretooluse gate" in lower
    assert "hmac-sha256" in lower
    assert "policy ∩ profile" in lower or "policy and the profile" in lower
    # Honest matrices: overnight is unverified everywhere; Claude Code chat only.
    assert "no overnight run has been verified" in lower
    assert "typed reply" in lower
    assert "chat only" in lower
    # The retired product name is kept out by the brand gate on every added
    # line; the README carries no lineage statement either.
    assert "Built on" not in _readme()


def test_product_docs_are_warding() -> None:
    product = (_REPO_ROOT / "PRODUCT.md").read_text(encoding="utf-8")
    assert product.startswith("# Warding")
    assert "The lamp stays on. The rules stay shut." in product
    assert "Built on" not in product
    assert "this checkout forks" not in product.lower()
    assert "Apache-2.0 fork" not in product
    lower = product.lower()
    for phrase in ("control plane", "side by side", "routes your models", "harness plane"):
        assert phrase not in lower, phrase
    overlay = (_REPO_ROOT / "WARDING.md").read_text(encoding="utf-8")
    assert overlay.startswith("# Warding")
    assert "## The NO-SAY list" in overlay
    assert "never a headline" in overlay
    # The one data home, stated once and carried by the overlay.
    assert "no fallback to another product's directory" in " ".join(overlay.split())
    brief = (_REPO_ROOT / "WORKING_BRIEF.md").read_text(encoding="utf-8")
    assert "| Product | **Warding**" in brief
    assert "| CLI | `warding`" in brief
    assert "assets/brand/build.py" in brief
    arch = (_REPO_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "one docked coding agent at a time" not in arch
    assert "Chat sessions run the one harness" in " ".join(arch.split())
    assert "never forwards provider traffic" in " ".join(arch.split())
    assert "The catalog forwards nothing" in arch
    roadmap = (_REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    assert "### M0" in roadmap and "### M5" in roadmap
    assert re.search(r"\b20\d\d-\d\d-\d\d\b", roadmap) is None, "roadmap carries a date"
    notice = (_REPO_ROOT / "NOTICE").read_text(encoding="utf-8")
    assert notice.lstrip().startswith("Warding")
    assert "this fork" not in notice.lower()
    assert "modified version of" not in notice
    tree = (_REPO_ROOT / "TREE.md").read_text(encoding="utf-8")
    assert tree.lstrip().startswith("# Warding")
    assert "this fork" not in tree.lower()
    assert not (_REPO_ROOT / "FORK.md").exists()
    adr = (_REPO_ROOT / "docs/adr/0008-product-rename-warding.md").read_text(encoding="utf-8")
    assert "Status: accepted" in adr
    assert "Builds on: [ADR 0001]" in adr
    first_adr = (_REPO_ROOT / "docs/adr/0001-product-identity.md").read_text(encoding="utf-8")
    assert "is a mature Apache-2.0 fork" not in first_adr
    adr_index = (_REPO_ROOT / "docs/adr/README.md").read_text(encoding="utf-8")
    assert "0008-product-rename-warding.md" in adr_index
    security = (_REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "five business days" in security
    assert "## Scope" in security
    assert "## Bypass reports" in security
    assert "48 hours" not in security


def test_cli_help_is_warding() -> None:
    assert cli_help.TOP_USAGE.startswith("warding ")
    rendered = cli_help.render_epilog()
    assert "warding up" in rendered
    assert "warding gateway" in rendered
    assert "  planes" in rendered
    assert "  up" in rendered
    assert f"Start {PRODUCT_NAME} on loopback" in rendered
    assert _RETIRED_PROSE not in rendered
    assert f"{_RETIRED_CLI} gateway" not in rendered


def test_packaged_docs_lead_with_warding() -> None:
    index = (_REPO_ROOT / "src/warding/docs/index.md").read_text(encoding="utf-8")
    assert index.lstrip().startswith("# Warding")
    assert "warding up" in index
    assert "A vendor agent CLI is optional" in index
    assert "kiro-cli is optional" not in index.split("## Core Capabilities", 1)[0]
    readme = (_REPO_ROOT / "src/warding/docs/README.md").read_text(encoding="utf-8")
    assert readme.lstrip().startswith("# Warding")
    gs = (_REPO_ROOT / "src/warding/docs/getting-started.md").read_text(encoding="utf-8")
    plain = gs.replace("`", "")
    assert "vendor agent CLI is optional" in plain
    assert "kiro-cli is optional" not in plain
    assert "scripts/get-warding.sh" in gs
    assert "```bash\ngit clone https://github.com/myrmitis/warding.git" in gs
    assert _RETIRED_DOWNLOAD_HOST not in gs
    assert _RETIRED_SLUG not in gs


def test_public_install_guides_point_at_this_repository() -> None:
    install = (_REPO_ROOT / "docs" / "guides" / "install.md").read_text(encoding="utf-8")
    windows = (_REPO_ROOT / "docs" / "guides" / "windows-install.md").read_text(encoding="utf-8")
    docker = (_REPO_ROOT / "docs" / "guides" / "docker.md").read_text(encoding="utf-8")
    compose = (_REPO_ROOT / "docker" / "compose.yaml").read_text(encoding="utf-8")
    assert _RETIRED_PROSE not in install
    assert _RETIRED_DOWNLOAD_HOST not in install
    assert f"{_RETIRED_CLI} gateway" not in install
    assert _RETIRED_SLUG not in install
    assert f"ghcr.io/{_RETIRED_ORG}" not in install
    assert "vendor agent CLI is optional" in install
    assert "scripts/get-warding.sh" in install
    assert "minimal_install.sh" in install
    assert _RETIRED_PROSE not in windows
    assert _RETIRED_DOWNLOAD_HOST not in windows
    assert f"{_RETIRED_CLI} gateway" not in windows
    assert "ghost family" not in windows
    assert f"ghcr.io/{_RETIRED_ORG}" not in docker
    assert "ghcr.io/myrmitis/warding" in docker
    assert f"ghcr.io/{_RETIRED_ORG}" not in compose
    assert "ghcr.io/myrmitis/warding:stable" in compose
    assert "container_name: warding" in compose
    ec2 = (_REPO_ROOT / "src/warding/cloud/templates/warding-ec2.yaml").read_text(encoding="utf-8")
    assert "https://github.com/myrmitis/warding.git" in ec2
    assert _RETIRED_SLUG not in ec2


def test_operator_install_scripts_link_warding(tmp_path: Path) -> None:
    script = _REPO_ROOT / "scripts" / "get-warding.sh"
    text = script.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n")
    assert "myrmitis/warding" in text
    # The update guard accepts this repository's own remotes and nothing else.
    assert "*myrmitis/warding*|*myrmitis/warding*) ;;" in text
    assert "acp" + "crew" not in text
    assert "minimal_install.sh" in text
    assert _RETIRED_PROSE not in text
    assert _RETIRED_CONCAT not in text
    assert _RETIRED_DOWNLOAD_HOST not in text
    assert _RETIRED_ORG not in text
    minimal = (_REPO_ROOT / "minimal_install.sh").read_text(encoding="utf-8")
    assert "Warding installed." in minimal
    assert "warding setup" in minimal
    assert "warding up" in minimal
    assert 'ln -sfn "$_venv/bin/warding" "$BIN_DIR/warding"' in minimal
    # The alias link is kept so existing launchers keep resolving.
    assert 'ln -sfn "$_venv/bin/warding" "$BIN_DIR/warding"' in minimal
    assert "A vendor agent CLI is optional." in minimal
    assert "👻" not in minimal
    assert _RETIRED_PROSE not in minimal
    assert _RETIRED_CONCAT not in minimal
    assert _RETIRED_ORG not in minimal
    assert "ollama pull" not in minimal
    checkout = (_REPO_ROOT / "install.sh").read_text(encoding="utf-8")
    assert "Warding installed." in checkout
    assert "warding setup" in checkout
    assert "warding up" in checkout
    assert 'ln -sf "$_venv/bin/warding" "$HOME/.local/bin/warding"' in checkout
    assert "A vendor agent CLI is optional" in checkout
    assert "👻" not in checkout
    assert "Your personal AI agent" not in checkout
    assert "kiro.dev" not in checkout
    assert _RETIRED_ORG not in checkout
    assert f"{_RETIRED_CLI} gateway" not in checkout
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["WARDING_SRC"] = str(tmp_path / "src")
    env["WARDING_BIN_DIR"] = str(tmp_path / "bin")
    result = subprocess.run(
        ["sh", str(script), "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "repo=https://github.com/myrmitis/warding.git" in result.stdout
    assert f"dest={tmp_path / 'src'}" in result.stdout
    assert "installer=minimal_install.sh" in result.stdout
    assert "next: warding setup && warding up" in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_dashboard_and_electron_chrome_are_warding() -> None:
    index = (_REPO_ROOT / "website" / "index.html").read_text(encoding="utf-8")
    loading = (_REPO_ROOT / "website" / "electron" / "loading.html").read_text(encoding="utf-8")
    manifest = (_REPO_ROOT / "website" / "public" / "manifest.json").read_text(encoding="utf-8")
    assert "<title>Warding</title>" in index
    assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml" />' in index
    assert f"<title>{_RETIRED_PROSE}</title>" not in index
    assert "<title>Warding</title>" in loading
    # The splash wordmark is an SVG, so its accessible name carries the product.
    assert 'id="title" role="img" aria-label="Warding"' in loading
    assert f">{_RETIRED_PROSE}</div>" not in loading
    # The splash draws the Ward Seal, the same geometry as the brand mark.
    assert _SEAL_SHAFT_PATH in loading
    assert '"name": "Warding"' in manifest
    assert '"short_name": "Warding"' in manifest
    i18n = (_REPO_ROOT / "website" / "src" / "i18n" / "index.ts").read_text(encoding="utf-8")
    assert "const DEFAULT_PRODUCT_NAME = 'Warding'" in i18n
    electron = (_REPO_ROOT / "website" / "electron" / "package.json").read_text(encoding="utf-8")
    # productName is an identifier that keeps its spelling (it names the macOS
    # bundle, the Windows executable and the build's post-gate target); the name
    # a person sees in the Dock, menu bar and dialogs is the display name.
    assert '"productName": "Warding"' in electron
    assert '"CFBundleDisplayName": "Warding"' in electron
    assert '"name": "warding-desktop"' in electron
    assert "control plane" not in electron
    for name in ("favicon.svg", "logo.svg"):
        svg = (_REPO_ROOT / "website" / "public" / name).read_text(encoding="utf-8")
        assert 'aria-label="Warding"' in svg


def test_agents_md_leads_with_warding() -> None:
    agents = (_REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.lstrip().startswith("# Rules")
    assert "this checkout is **Warding**" in agents
    assert "The product is **Warding**" in agents
    assert "**CLI:** `warding`" in agents
    assert "kiro-cli is REQUIRED" not in agents
    assert f"{_RETIRED_PROSE} is an open-source personal AI agent" not in agents
    assert "this is a public OSS fork" not in agents.lower()


def test_github_issue_templates_name_the_cli() -> None:
    config = (_REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8")
    bug = (_REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text(encoding="utf-8")
    feature = (_REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml").read_text(
        encoding="utf-8"
    )
    docs = (_REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "documentation.yml").read_text(
        encoding="utf-8"
    )
    assert _RETIRED_SLUG not in config
    assert _RETIRED_SLUG not in bug
    assert _RETIRED_SLUG not in feature
    assert _RETIRED_SLUG not in docs
    assert f"{_RETIRED_CONCAT} version" not in bug
    assert "Warding version" in bug
    assert "warding --version" in bug
    assert "warding up" in bug
    assert "Warding" in docs
    assert "Channels help" not in docs


def test_ownership_banner_and_wrappers_are_warding() -> None:
    maintainers = (_REPO_ROOT / "MAINTAINERS.md").read_text(encoding="utf-8")
    codeowners = (_REPO_ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    banner = (_REPO_ROOT / "assets" / "banner.svg").read_text(encoding="utf-8")
    seal = (_REPO_ROOT / "assets" / "brand" / "mark.svg").read_text(encoding="utf-8")
    assert "@laqaer" in maintainers
    assert f"{_RETIRED_CLI}-team" not in maintainers
    assert _RETIRED_SLUG not in maintainers
    assert "*                                   @laqaer" in codeowners
    assert f"{_RETIRED_CLI}-team" not in codeowners
    assert 'aria-label="Warding: The lamp stays on. The rules stay shut."' in banner
    assert "<title>Warding: The lamp stays on. The rules stay shut.</title>" in banner
    assert "Kiro" not in banner
    assert _RETIRED_PROSE not in banner
    assert 'aria-label="Warding"' in seal
    assert _SEAL_SHAFT_PATH in seal
    wrapper = (_REPO_ROOT / "bin" / "warding").read_text(encoding="utf-8")
    assert "# Warding CLI wrapper." in wrapper
    assert "Warding virtual environment not found" in wrapper
    assert f"{_RETIRED_PROSE} virtual environment" not in wrapper
    assert 'for name in "$INVOKED" warding; do' in wrapper
