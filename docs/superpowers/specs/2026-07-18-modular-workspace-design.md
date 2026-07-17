# Modular Workspace Redesign

**Date:** 2026-07-18

## Overview

Decouple the 3-stage linear wizard into independent, reusable modules. Scripts, voices, and podcasts become first-class artifacts that can be created, saved, browsed, and combined independently.

## Pages

| Route | Page | Purpose |
|-------|------|---------|
| `/` | Dashboard | Quick stats, recent items, action buttons |
| `/scripts` | Script Library | List scripts, "New from URL" form |
| `/scripts/<id>` | Script Detail | View full dialog |
| `/voices` | Voice Library | Browse, create (clone/design), test, delete voices |
| `/studio` | Podcast Studio | Pick script + Voice A + Voice B, generate |
| `/projects` | History | Existing podcast history |
| `/project/<id>` | Podcast Detail | Existing detail page |

## Data Stores

All user-generated data:

| Store | Location | Format |
|-------|----------|--------|
| Scripts | `web/data/scripts/{id}.json` | JSON (article_url, title, dialog, created_at) |
| Projects | `web/data/projects/{id}.json` | JSON (existing) |
| Voices | `voices/{name}.pt` + `index.json` | torch + JSON (existing) |

## Backend

### Script Store (`scripts_store.py`)
- `load_scripts()` -> list of script summaries
- `save_script(dict)` -> id
- `get_script(id)` -> dict or None
- `delete_script(id)` -> void

### Script Endpoints
- `GET /api/scripts` -> list of script summaries (no dialog payload)
- `GET /api/scripts/<id>` -> full script with dialog
- `POST /api/scripts/create` `{url}` -> generates dialog via ScriptMaker, saves, returns summary
- `DELETE /api/scripts/<id>`

### Voice Endpoints (already built)
- `GET /api/voices/library` -> list (already exists)
- `POST /api/voices/save`, `/api/voices/select`, `/api/voices/delete` (already exist)
- `POST /api/voice-design` (already exists)
- `POST /api/upload-reference` (already exists)
- **NEW:** `POST /api/voices/preview` `{display_name, text}` -> audio/wav response for testing

### Studio Endpoint
- `POST /api/studio/generate` `{script_id, voice_a_name, voice_b_name}` -> SSE stream with progress, saves project on completion

### Dashboard
- `GET /api/dashboard` -> `{scripts: N, voices: N, projects: N, recent_scripts: [...], recent_voices: [...], recent_projects: [...]}`

## Frontend

### Navigation
All pages share a top nav: `Dashboard | Scripts | Voices | Studio | History`

### Dashboard (`dashboard.html`)
- 3 stat cards: Scripts count, Voices count, Projects count
- 3 lists: Recent scripts, recent voices, recent podcasts (last 5 each)
- Quick-action buttons: "New Script", "Create Voice", "Generate Podcast"

### Scripts (`scripts.html`)
- Form at top: URL input + "Generate Script" button + spinner
- List below: script cards with title, date, URL
- Each card: click to view detail, delete button
- Client-side search filter

### Script Detail (`script.html`)
- Article title + URL link
- Full dialog rendered as speaker cards (reuse existing format)
- "Use in Studio" button → redirects to /studio with script pre-selected

### Voices (`voices.html`)
- Two columns: Speaker 'A-like' / Speaker 'B-like' (or unified list)
- Each column: list of saved voices with type badge, description
- "Create New Voice" button → opens inline panel (clone/design tabs)
- "Test" button per voice → plays short sample audio via /api/voices/preview
- Delete button per voice

### Studio (`studio.html`)
- 3 selectors:
  1. Script dropdown/picker (from saved scripts)
  2. Voice A dropdown (from saved voices)
  3. Voice B dropdown (from saved voices)
- "Generate Podcast" button
- SSE progress bar + status
- On complete: audio player, save as project, link to /project/<id>

## Files Changed

| File | Action |
|------|--------|
| `scripts_store.py` | New — script CRUD |
| `web/app.py` | Add script, studio, dashboard, voice preview endpoints. Remove session-based wizard endpoints (or keep for compat). Replace `/` route from wizard to dashboard. |
| `web/templates/dashboard.html` | New |
| `web/templates/scripts.html` | New |
| `web/templates/script.html` | New |
| `web/templates/voices.html` | New |
| `web/templates/studio.html` | New |
| `web/templates/index.html` | Repurpose or remove (old wizard) |
| `web/templates/projects.html` | Add nav bar |
| `web/templates/project.html` | Add nav bar |
| `web/static/style.css` | Add new styles, nav bar styles |
| `web/static/script.js` | Remove old wizard code, keep shared utilities |

## Removed

- 3-stage wizard UI (index.html)
- Session-based state management (voices, dialog, stage)
- `/api/generate-clones` (mock endpoint, unused)
- Old `generate-clones-btn` / voice-design submit flow from script.js
