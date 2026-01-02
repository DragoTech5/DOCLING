# Docling Knowledge Hub - Essential Project Memory

## Server Configuration
- **Native Port**: 8200 (always use this port)
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port 8200 --reload`
- If port 8200 is occupied: `pkill -f "uvicorn app.main" && sleep 2` then restart

## Current Work
- **Branch**: `feature/knowledge-archive-twa` - Telegram Mini App for combined knowledge archive
- **Active Bug**: Multi-document sources only showing 1 source when 2+ documents selected
  - Issue Location: `/app/services/chat_service.py:938-1003` - `_extract_cited_sources()` function
  - Root Cause: Function filters sources by explicit `[1]`, `[2]` citations; drops sources without explicit citations
  - Status: Root cause identified, fix not yet implemented
  - Test Status: Needs isolated unit testing + multi-doc browser testing

## Tech Stack
- **Backend**: FastAPI (port 8200)
- **Frontend**: React 18 + TypeScript + Vite + Zustand + Tailwind CSS
- **Databases**: PostgreSQL with pgvector
  - MAG-LIB: port 5432, `magick_knowledge` (6,377 docs, 534k chunks)
  - BIBLIOTHEK: port 5433, `bibliothek_knowledge` (2,701 docs, 1.8M chunks)
- **Embeddings**: BAAI/bge-large-en-v1.5 (1024 dimensions)
- **Chat**: OpenAI API (GPT-4/Claude via API)

## Critical File Locations
- **Mini App**: `/home/kanat/DEVELOPER/N8N-SERVERS/DOCLING/telegram-mini-app/`
- **Backend API**: `/app/api/telegram.py`
- **Chat Service**: `/app/services/chat_service.py`
- **Frontend Store**: `/telegram-mini-app/src/stores/chatStore.ts`
- **Archive Page**: `/telegram-mini-app/src/pages/ArchivePage.tsx`
- **Chat Page**: `/telegram-mini-app/src/pages/ChatPage.tsx`

## Testing & Deployment

### Clean Build + Deploy Procedure
After ANY frontend code changes:
```bash
cd /home/kanat/DEVELOPER/N8N-SERVERS/DOCLING/telegram-mini-app
rm -rf dist node_modules/.vite
npm run build

pkill -f "uvicorn app.main"
sleep 2
source ./venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8200 --reload > uvicorn.log 2>&1 &
sleep 3
```

### Browser Testing Protocol
- **Always test in actual Telegram Mini App** (not localhost only)
- Use Chrome DevTools Protocol (CDP) on port 9222 for automation
- Use WebSocket connections to `http://127.0.0.1:9222/json` for browser control
- Take screenshots to document test results

### Known HTTP 401 Error
- Caused by missing rebuild of dist files or server restart
- Solution: Follow clean build procedure above
- Related: `/api/telegram/documents` endpoint requires `X-Telegram-Init-Data` header

## Cloudflare Tunnel & Telegram Menu Button
- **Current Bot**: @DoclingKB_bot (@Akasha_AI_bot)
- **Current Tunnel URL**: `https://select-signature-lloyd-trails.trycloudflare.com/twa/` (✅ Updated Dec 30, 2025)
- **Menu Button Text**: "🎓 Open Akasha AI" (configured via `scripts/setup_telegram_menu_button.py`)

### If Tunnel Expires
```bash
cd /home/kanat/DEVELOPER/N8N-SERVERS/DOCLING
pkill -f "cloudflared tunnel --url"
sleep 2
nohup cloudflared tunnel --url http://localhost:8200 > /tmp/cloudflared.log 2>&1 &
sleep 5
TUNNEL_URL=$(tail -20 /tmp/cloudflared.log | grep "trycloudflare" | grep -oP 'https://[^ ]*')
echo "New URL: $TUNNEL_URL"
# Then update Telegram menu button with new URL
```

## Known Issues & Fixes

### Document Selection Persistence ✅ FIXED (Commit 476fb79)
- Issue: Document selection didn't persist when switching between Archive and Chat
- Fix: Removed blanket `initialized` guard in ChatPage.tsx useEffect
- Status: VERIFIED WORKING

### Conversation Memory ✅ FIXED (Commits d059f36, f885e10)
- Issue: Follow-up messages had no context from first message
- Fixes: Frontend loads conversation after first message, backend fetches history
- Status: VERIFIED WORKING

### Multi-Document Sources ❌ NOT YET FIXED
- Issue: When selecting 2+ documents, AI response only shows 1 source
- Root Cause: `_extract_cited_sources()` filters by explicit `[1]`, `[2]` citations
- Fix Status: Identified but not yet implemented
- Next Steps: Unit test + browser testing with >2 documents

## Project Memory Archives
- **Full History**: `docs/PROJECT_MEMORY_ARCHIVE.md` - Complete historical context
  - Previous implementations
  - Processing details
  - All resolved issues
  - Architecture decisions
- **Current Doc**: This file (CLAUDE.md) - Essential info only

## Quick References
- **Archon TWA Project ID**: `1da841e4-785f-49c4-91d4-e4e451b78dbb`
- **Archon PDF Processing Project ID**: `758be85c-84fc-46b8-8441-f7009276ae0d`
- **Subscription Tiers** (Actual Implementation):
  - Free: 3 q/day, $0
  - Starter: 25 q/day, $9.99/month (430 Stars)
  - Pro: 60 q/day, $19.99/month (860 Stars)
  - Unlimited: Unlimited q/day, $49.99/month (2298 Stars)
