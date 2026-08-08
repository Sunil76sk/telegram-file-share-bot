# AGENTS.md - Telegram File Share Bot

## Tech Stack
- Python 3.11+, Pyrogram 2.x (MTProto NOT Bot API)
- MongoDB Motor (async), Redis aioredis
- FastAPI, Docker, GitHub Actions
- Payments: Razorpay / Stripe / UPI / Telegram Stars

## Coding Rules
- All functions must be async/await - no blocking I/O
- Type hints on every function signature
- Use loguru for logging, not print()
- Max line length: 100 chars (PEP 8)

## Pyrogram Rules
- Always use @app.on_message(filters.X) pattern
- Always use filters.private or filters.group explicitly
- Handle FloodWait on EVERY Telegram API call:
  except FloodWait as e: await asyncio.sleep(e.value)

## MongoDB Rules
- Collections: files, links, users, analytics, payments
- Create indexes in startup function, not inline
- Never use .find() without .limit() - always paginate
- Always use $set - never replace entire documents

## File Naming
- Handlers: bot/handlers/<feature>.py
- Models:   bot/models/<collection>.py
- Services: bot/services/<service>.py
- Tests:    tests/test_<module>.py

## Git Conventions
- feat: add password protection for links
- fix: handle FloodWait in batch uploads
- chore: update requirements.txt
- Branch: feat/<feature>, fix/<bug>, chore/<task>
- Never commit .env - always use .env.example

## GitHub Actions Rules
- Runner: ubuntu-latest always
- Secrets: ${{ secrets.KEY }} never hardcode
- CI must pass before merge to main
- Deploy: docker-compose pull && docker-compose up -d

## Testing Rules
- Every handler needs at least one pytest test
- Use pytest-asyncio for async tests
- Mock Motor - never hit real MongoDB in tests
- Coverage minimum: 70% per module

## Tier Gating
- FREE: no gate
- PRO+: plan in ["pro","creator","business","enterprise"]
- CREATOR+: plan in ["creator","business","enterprise"]
- Use tier_required() decorator on all premium features

## Security Rules
- Hash passwords with bcrypt before storing
- Hash IPs with SHA-256 before analytics storage
- ALWAYS verify payment webhook signatures
- Validate all user input - never pass raw to MongoDB

## Do NOT
- Do NOT use sync requests library - use httpx async
- Do NOT store Telegram file_ids permanently (they expire)
- Do NOT skip FloodWait handling
- Do NOT deploy without running tests