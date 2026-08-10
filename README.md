# admin-csr-tech

FLT Admin, CSR, and Technical Team portal — a Flask application for managing customer support chats, CSR workflows, and technical tickets.

## Features

- **Admin dashboard** — CSR roster, chat monitoring, technical team management, ticket workspaces, activity timeline
- **CSR dashboard** — Customer chats (New / Mine / Others), messaging, ticket creation, tech chat, archive
- **Tech dashboard** — Ticket queue, status updates, CSR messaging, presence (online/offline)

## Project structure

```
app.py                 # Flask backend (routes, APIs, auth, presence)
templates/             # Admin, CSR, and Tech HTML dashboards + login pages
static/                # Admin dashboard CSS/JS and shared theme
schema/                # SQLite and Supabase schema files
scripts/               # Migration utilities
flutter_api_docs/      # API documentation for Flutter/mobile clients
ecosystem.config.js    # PM2 process config
requirements.txt       # Python dependencies
.env.example           # Environment variable template (copy to .env)
```

## Setup

1. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your values.

3. Run the app:

   ```bash
   python app.py
   ```

   Or with PM2:

   ```bash
   pm2 start ecosystem.config.js
   ```

## Login routes

| Portal | URL |
|--------|-----|
| Admin  | `/admin/login` |
| CSR    | `/csr/login` |
| Tech   | `/tech/login` |

## Notes

- Do not commit `.env`, database files under `instance/`, or the `.venv/` directory.
- The app integrates with the FLT chat widget / central relay for live customer messaging.
