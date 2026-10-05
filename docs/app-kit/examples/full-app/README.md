# My App — Full-Featured Example

Demonstrates all Junction app capabilities: UI page, agent, skill, cron job,
real-time events, and nav badge.

## Install

```bash
cd full-app/ui && npm install && npm run build
junction app install ./full-app
junction app enable my-app
```

## Features

- Dashboard page with ticket table and stat cards
- Background agent that checks tickets every 5 minutes
- Real-time notification handling
- Sidebar badge showing urgent ticket count
