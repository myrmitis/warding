"""Provider seams for the Meetings app.

Two extension points, both shaped like ``warding.embeddings``'s
``EmbeddingBackend`` + ``register_embedding_backend``: an ABC plus a
name-keyed factory registry, with exactly ONE implementation shipped here.

* :mod:`tasks` — where a reviewed action item gets filed. Ships a local
  task ledger.
* :mod:`calendar` — where upcoming meetings come from. Ships a stdlib
  iCalendar (``.ics``) reader.

The point of the seams is that an out-of-tree package can register its own
provider (an issue tracker, a hosted calendar service) without patching this app.
Nothing in the core branches on a provider name.
"""

from warding.apps.builtins.meetings.backend.providers.calendar import (  # noqa: F401
    CalendarEvent,
    CalendarProvider,
    available_calendar_providers,
    get_calendar_provider,
    register_calendar_provider,
)
from warding.apps.builtins.meetings.backend.providers.tasks import (  # noqa: F401
    TaskDraft,
    TaskProvider,
    TaskRef,
    available_task_providers,
    get_task_provider,
    register_task_provider,
)
