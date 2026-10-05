# Post-Launch Removals

Code that exists **only** to carry pre-launch users across a data migration, and
should be deleted once the product ships to net-new users (who have no legacy
data to migrate). Track each item here; delete the code and its row together.

> Why a doc and not a `TODO`: these removals span multiple modules and are safe
> to do **only** after launch (they would strand a pre-launch developer mid-
> migration if removed early). Grouping them keeps the "is it safe to delete
> yet?" decision in one place.

## Pending removals

None. Junction has exactly one data home, `~/.junction` (overridden by
`JUNCTION_HOME`), and carries no migration code, no fallback to another
directory, and no older data-home spellings on the security floor. Add a
section here when new migration-only code lands.
