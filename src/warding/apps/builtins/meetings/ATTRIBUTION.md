# Attribution

The Meetings app was originally written by **adunuthu** as a standalone
app named **Meetings**, distributed as its own package with its own backend
server, UI bundle, and agent specs. This builtin is a port of that work into this
repository.

`app.json`'s `author` field is unchanged — the original author remains the
author of record.

## What changed in the port

The meeting lifecycle, the batching agent dispatcher, the domain dictionary, the
task-review flow, and the multi-agent panel UI are a faithful port. Four couplings
were replaced with generic seams:

| Area | This port |
|---|---|
| Filing action items | A `TaskProvider` seam (`backend/providers/tasks.py`) with one shipped implementation: a local task ledger. An organization registers its own provider out of tree. |
| Reading the calendar | A `CalendarProvider` seam (`backend/providers/calendar.py`) with a stdlib iCalendar (`.ics`) reader — a local file or a published `https://` URL. |
| Speech-to-text | The gateway's own streaming speech-to-text (`/api/ws/stt`). |
| Server and scheduling | In-gateway routes under `/api/apps/meetings/*`, and in-process agent dispatch through the shared session manager. The data-directory self-heal is Python that runs at app startup; a builtin app versions with the package, so there is no update check. |
