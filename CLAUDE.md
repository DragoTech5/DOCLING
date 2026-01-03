# Docling Knowledge Hub - Essential Project Memory

## Server Configuration
- **Native Port**: 8200 (always use this port)
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port 8200 --reload`
- If port 8200 is occupied: `pkill -f "uvicorn app.main" && sleep 2` then restart

## Current Work - Infrastructure Fixes + E2E Testing ✅ COMPLETE
- **Branch**: `feature/railway-nas-hybrid-deployment` - Telegram Mini App with NAS persistence
- **Status**: ✅ SMB mount persistence + Browser E2E testing complete

### Latest E2E Test Results (2026-01-02)
- ✅ **HomePage**: Tier display, saved conversations (5), usage stats
- ✅ **ArchivePage**: 9,078 documents, pagination (1/303), A-Z navigation, collection indicators (MAG-LIB/BIBLIOTHEK)
- ✅ **ChatPage**: Message sending, input/output working, Save/Share buttons visible
- ✅ **HistoryPage**: Saved conversations loading and accessible
- ✅ **PricingPage**: All 4 tiers (Free/Starter/Pro/Unlimited), correct pricing ($9.99/$19.99/$49.99), payment options
- ✅ **SharePage**: Proper error handling for invalid/expired share tokens
- ✅ **Mobile Responsive**: iPhone 13 portrait (390x664) layout working correctly
- ✅ **Navigation**: All pages accessible via bottom navigation buttons
- ⚠️ **Console**: 23 minor 404 errors for static resources (images/fonts) - does not affect functionality
  - Task 1-10: Core implementation (favicon, tiers, endpoints, UI)
  - Task 11: ✅ Profile response & quota check middleware
  - Task 12: ✅ Download analytics tracking
  - Task 13: ✅ Integration testing (all features verified)
  - Task 14: ✅ Documentation & deployment

## Tech Stack
- **Backend**: FastAPI (port 8200)
- **Frontend**: React 18 + TypeScript + Vite + Zustand + Tailwind CSS
- **Databases**: PostgreSQL with pgvector
  - MAG-LIB: port 5432, `magick_knowledge` (6,377 docs, 534k chunks)
  - BIBLIOTHEK: port 5433, `bibliothek_knowledge` (2,701 docs, 1.8M chunks)
- **Embeddings**: BAAI/bge-large-en-v1.5 (1024 dimensions)
- **Chat**: OpenAI API (GPT-4/Claude via API)

## New Features - PDF Downloads & Single Book Chat

### PDF Downloads
- **Endpoint**: `GET /api/telegram/download/{document_id}`
  - Format: `maglib:ID` or `bibliothek:ID`
  - Returns FileResponse with user-friendly filename
  - Enforces daily quota per tier before streaming
  - Returns 429 when quota exhausted
  - Logs all downloads (success/failure) with analytics
- **UI**: Download button in document modal (Archive page)
- **Quota**: Tier-based daily limits with auto-reset at UTC midnight
  - Free: 1 PDF/day
  - Starter: 3 PDFs/day
  - Pro: 12 PDFs/day
  - Unlimited/Enterprise: Unlimited

### Single Book Chat
- **Feature**: Click "Chat with This Book" button in modal
- **Behavior**: Creates new conversation with only that document
- **Implementation**: Uses existing `/conversations/create` with single pdf_id

## Critical File Locations
- **Mini App**: `/home/kanat/DEVELOPER/N8N-SERVERS/DOCLING/telegram-mini-app/`
- **Backend API**: `/app/api/telegram.py` (lines 695-835 for download endpoint)
- **Repository**: `/app/db/telegram_repository.py` (quota management functions)
- **Database Models**: `/app/db/models.py` (pdf_downloads table + analytics fields)
- **Frontend Store**: `/telegram-mini-app/src/stores/chatStore.ts`
- **Archive Page**: `/telegram-mini-app/src/pages/ArchivePage.tsx` (download button)
- **Chat Page**: `/telegram-mini-app/src/pages/ChatPage.tsx`
- **Pricing Page**: `/telegram-mini-app/src/pages/PricingPage.tsx` (displays download limits)

## Testing & Deployment

### ⚠️ CRITICAL: TELEGRAM BOT TESTING ONLY - NOT WEB TUNNEL
**MANDATORY RULE**: ONLY test on the ACTUAL TELEGRAM BOT `https://web.telegram.org/k/#@AkashaAIHub_bot`
- **Correct URL**: `https://web.telegram.org/k/#@AkashaAIHub_bot` (the real Telegram bot that users use)
- **WRONG**: `https://select-signature-lloyd-trails.trycloudflare.com/twa/` (Cloudflare web tunnel - can mislead about actual deployment status)
- **Why**: The web tunnel and Telegram bot are SEPARATE DEPLOYMENTS. Web tunnel may work while bot is broken. Always test what users actually use.
- **Verification**: Test ONLY in actual Telegram bot. User responses = truth. Web tunnel = irrelevant.
- **Test Scenario**: Open Telegram bot → select document → ask specific question → verify context-aware response (not generic "couldn't find information")
- **Success Criteria**: MUST run 4 consecutive tests with 4 DIFFERENT documents in ACTUAL TELEGRAM BOT, each returning context-aware responses. Generic responses = FAILURE. Only 4/4 all-pass = system is successful.

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

### 🔬 Universal Browser E2E Testing Protocol

**Reference Doc:** `UNIVERSAL_BROWSER_TESTING_PLAYWRIGHT_MCP.md` in Archon KB

#### Success Criteria
- ✅ Tested in actual debug browser on port 9222
- ✅ Navigated through webapp like a human user
- ✅ Feature works end-to-end in real browser with session state

#### 3-Phase Testing Strategy

**Phase 1: Code Validation (Fastest)**
- No browser needed
- Check syntax, imports, API endpoints
- Duration: Seconds to 1 minute

**Phase 2: Playwright MCP Testing (Fast Iteration)**
- Use Playwright MCP tools for quick UI testing
- Create new browser instances per test
- Good for rapid iteration
- Duration: 30 seconds to 2 minutes

**Phase 3: Debug Browser Verification (Final Truth - REQUIRED)**
- Connect to Chrome debug browser on port 9222
- Use existing session state (cookies, localStorage, auth)
- Test with real user login/state
- Only way to verify actual UX
- Duration: 1-3 minutes

#### Browser Launch (Automatic)
Browser was started with:
```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

#### CDP Connection (Node.js)
```javascript
const { chromium } = require('playwright');

async function testWithDebugBrowser() {
    // Connect to debug browser (preserves session)
    const browser = await chromium.connectOverCDP('http://localhost:9222');
    const page = browser.pages()[0]; // Use first/active tab

    // Now test with real session state
    await page.goto('https://your-app-url/chat');
    // Test your feature here...

    await browser.close();
}
```

#### Available Tools
- **Playwright MCP**: Quick testing, new instances
- **Browser MCP**: Alternative automation
- **CDP Direct**: Maximum control via WebSocket

#### Playwright MCP Quick Reference
- `mcp__playwright__playwright_navigate` - Navigate to URL
- `mcp__playwright__playwright_click` - Click element (CSS selector)
- `mcp__playwright__playwright_fill` - Fill input field
- `mcp__playwright__playwright_screenshot` - Capture screenshot
- `mcp__playwright__playwright_get_visible_text` - Get page text
- `mcp__playwright__playwright_console_logs` - Get console output

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

### PDF Download Quota Management ✅ IMPLEMENTED
- Auto-reset at UTC midnight (no manual reset needed)
- Returns 429 if quota exhausted
- Analytics tracked for all downloads (success/failure)
- Response time measured for performance analysis
- Status: FULLY OPERATIONAL

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
- **Subscription Tiers** (Queries + PDF Downloads):
  - Free: 6 q/day + 1 PDF/day, $0
  - Starter: 25 q/day + 3 PDFs/day, $9.99/month (430 Stars)
  - Pro: 60 q/day + 12 PDFs/day, $19.99/month (860 Stars)
  - Unlimited: ∞ q/day + ∞ PDFs/day, $49.99/month (2298 Stars)
  - Enterprise: ∞ q/day + ∞ PDFs/day, $0 (dev whitelist only)

## New API Endpoints (PDF Download Feature)
- `GET /api/telegram/profile` - Updated with download quota fields
  - Returns: `downloadsUsed`, `downloadsRemaining`, `downloadQuotaResets`, `dailyDownloadLimit`
- `GET /api/telegram/download/{document_id}` - Download PDF with quota enforcement
  - Status 429: Quota exhausted
  - Status 404: Document or file not found
  - Status 200: File streaming with analytics logging

## Database Changes
- **New Table**: `pdf_downloads` - Download history for analytics
  - Fields: telegram_user_id, document_id, document_title, collection, file_size_mb, ip_address, user_tier, response_time_ms, success, error_type, downloaded_at
  - Indexes: user_id, document_id, downloaded_at
- **Altered Tables**: `telegram_users` - Added download quota fields
  - Fields: downloads_used, downloads_remaining, download_quota_resets_at
