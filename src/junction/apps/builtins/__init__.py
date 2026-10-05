# Built-in apps package.

BUILTIN_NAMES: list[str] = [
    "auto_improvement",
    "auto_research",
    "auto_triage_pipeline",
    "code_review_sage",
    "desk_companion",
    "issue_radar",
    "meetings",
    "ops_mission_control",
    "papyrus",
    "mochi",
    "personal_shopper",
    "pptx_maker",
    "spec_builder",
]

# Names of builtin apps whose functionality was folded into the core. Startup
# removes the stale installed metadata of any app listed here (its data/ is kept).
_MIGRATED_BUILTINS: list[str] = []
