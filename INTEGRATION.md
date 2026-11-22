# STILL-care integration status and operator instructions

This is a partial integration, not a finished production application. No changes have been pushed to GitHub in this implementation turn. Existing uncommitted intelligence_model and documentation work was preserved.

## Implemented

- Central Supabase client using public environment variables, persisted sessions, SDK token refresh, email/password login, member signup, email confirmation redirect, recovery email request and password update. Existing two-column login artwork and styling retained; new registration/recovery forms added. Profile page content was replaced with editable real data cards using existing styling (not pixel-identical).
- Protected patient/consultant route trees. Consultant approval checked in database, never from role selector or editable auth metadata. Demo perspective switch and demo credential controls removed from active app.
- SQL migration creates profiles, consultants, consultant_requests, consultant_assignments and notifications with RLS and restricted column update grants. Account creation always produces patient role. Verified patients request approved IDs through RPC. Review RPC locks request and atomically creates assignment and notification; rejected requests never create assignments. Patient has at most one assignment.
- Real profile name/photo URL/description persistence, copy consultant ID, count of assigned patients, logout. Request and notification management available on profiles; patient connection page also supports requests.
- Patient sessions and authorized consultant sessions read from local authenticated API. No mockData imports remain in active API adapters. Empty local histories return empty arrays.
- Written reflections use existing module 04 and local qwen2.5:7b-instruct in Ollama. Reports/graphs stored locally, accessible only after Supabase Auth server verifies bearer token and RLS-backed assignment RPC verifies access. No sensitive report uploads to Supabase.
- Personalization narrative stored separately locally and supplied as untrusted user context, not system instructions. Explicit POST /personalization/extract uses module 06 to create a separate structured-facts file; narrative is never replaced. Automated profile extraction/merging during voice sessions remains unconnected.
- Session report/graph panel appears together for latest patient session and selectable consultant sessions.

## Apply database migration (NOT applied automatically)

Live probe: existing Auth settings returned HTTP 200; profiles API returned HTTP 404/PGRST205. No authenticated SQL/database administrator connection is available in this environment. Public publishable keys cannot apply DDL.

1. Open existing STILL-care project in Supabase Dashboard > SQL Editor.
2. Run all of supabase/migrations/202611220001_identity_assignments.sql once. Migration is transactional and is not intended to be rerun over existing tables.
3. In Authentication > URL Configuration set Site URL to http://localhost:3000 for local testing. Add http://localhost:3000/login, http://localhost:3000/reset-password and corresponding actual deployment URLs to redirect allow list. If using 127.0.0.1 also add that origin's URLs.
4. Enable email/password provider and confirm-email requirement. Configure SMTP and test actual confirmation/recovery email delivery; no delivery has been verified here.
5. Create/invite the first consultant in Authentication > Users, complete verification, replace email in supabase/provision_consultant.sql and run it in SQL Editor as administrator. Copy generated Consultant ID. Never implement public self-promotion or ship administrator secrets in Vite variables.
6. Register a patient with that Consultant ID. After verification sign in using the same browser; pending ID is retained there until RPC succeeds. On a different browser enter the ID on Talk to consultant or Profile. Open consultant Profile to accept/reject requests and read notifications.

## Run locally (PowerShell from repository root)

Environment is ignored by git. .env.local requires VITE_SUPABASE_URL, VITE_SUPABASE_PUBLISHABLE_KEY and VITE_API_URL=http://localhost:8001. Backend reuses public Supabase values to validate users online; no service-role key required. Optional FRONTEND_ORIGINS is comma-separated. STILL_PRIVATE_DIR selects private filesystem storage; protect its OS permissions and encrypted backups.

Frontend:
```powershell
npm ci
npm run dev -- --host 127.0.0.1
```
Backend, separate terminal:
```powershell
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
.venv/Scripts/python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```
Ollama, separate terminal if not running:
```powershell
ollama serve
ollama pull qwen2.5:7b-instruct
```
Use http://localhost:3000 (or allowlisted 127.0.0.1). Port 8000 was already occupied, so this integration uses 8001. Do not expose intelligence_model/api directly: its upstream design assumes an authenticated parent and this integration does not mount its unprotected routes.

## Tests actually run

- npm audit initially reported 5 vulnerabilities; two compatible npm audit fix runs reduced this to 0. npm install/build executed esbuild successfully; no install-script permissions were broadly enabled.
- npm run lint passed after changes.
- npm run build passed; output has a bundle-size warning.
- python -m unittest backend.test_app -v: 8 passed (dependency-isolated boundary tests, not live Supabase RLS tests). Covers no token, empty history, assigned/unassigned access, narrative isolation, invalid artifacts, empty input and model failure without session persistence. Windows SQLite handle cleanup issue discovered and corrected.
- python -m unittest discover -s chatbot/06_case_profile/tests -v: 13 passed. spaCy unavailable; existing regex fallback warning emitted.
- Voice tests attempted: setup blocked by Windows Application Control rejecting PyAV native DLL. No voice tests passed in this run.
- Frontend server returned HTTP 200; backend /health returned 200; /sessions without token returned 401. Backend started successfully on 8001.
- Existing Supabase Auth settings reachable; database schema missing. Ollama tags endpoint returned 200 and qwen2.5:7b-instruct installed.

## Remaining work and limitations

- Live account registration, email delivery/verification, wrong-password, recovery, session refresh, consultant approval and RLS isolation still need end-to-end tests after migration and SMTP/redirect setup. No real account was created during this run.
- Browser voice transport, microphone recording/upload validation, per-turn reply lifecycle, acoustic/emotion modules 01-03 and 05 HTTP integration are unfinished. The simulated voice UI was removed and now explains unavailability; CLI voice pipeline remains intact. Do not interpret written sessions as acoustic assessments.
- Messaging, appointment scheduling, intervention logging and recommendations are unfinished. Read adapters expose no records; write endpoints do not fake success. Do not use these flows operationally until implemented. Existing ancillary screens still need a complete UI audit for static design copy and unsupported actions.
- Distress color and alert policy requires explicit approval. Actual scores appear in generated graph; records stay neutral and trends unknown. No invented clinical thresholds, automatic distress alerts, or recommendations are generated. Low scores do not establish safety.
- Some legacy insight components still assume color-based trend mappings; full redesign-free numerical score/history integration and all-session patient report navigation remain unfinished.
- Original narrative is supplied to future written report generation; full module 06 case-memory lifecycle and conversational personalization remain unfinished.
- Profile photos currently support HTTPS URL entry, not binary uploads. Assigned consultant details are available via adapter; profile presentation still needs completion.
- Remember-device checkbox currently does not change SDK persistence behavior; sessions persist until logout. Registration consultant ID persists in local browser until login and is validated after verification.
- No browser visual regression/accessibility review, live SQL migration execution or production security review was performed. API lacks production request throttling and concurrency/job lifecycle; local clinical files need operator-managed access controls/encryption.

## Additional verified inference check

A synthetic, non-patient reflection was processed through the real local module 04 and installed Ollama model. It returned an actual distress score of 2, persisted the session report, and produced mental_state.png successfully in a temporary private store. This test bypassed live Supabase authorization through a patched identity boundary; it is not a live authenticated end-to-end test. Test files were cleaned up. Structured background extraction is available from the member profile after saving the narrative, and subsequent written reports receive both the original narrative and separately extracted facts as untrusted context.

## Files changed in this integration

New: backend/__init__.py, backend/app.py, backend/requirements.txt, backend/test_app.py; supabase/migrations/202611220001_identity_assignments.sql; supabase/provision_consultant.sql; src/lib/supabase.ts; src/components/RequireAuth.tsx, AssignmentPanel.tsx, SessionArtifacts.tsx; src/pages/auth/AccountFlow.tsx; INTEGRATION.md.

Modified: package.json/package-lock.json; .env.example/.gitignore; src/App.tsx; src/api/patientApi.ts and supervisorApi.ts; authentication LoginPage; patient and consultant ProfilePage; patient SupervisorConnectionPage, ConversationPage and DashboardPage; consultant DashboardPage, PatientDetailPage and TrendsPage; both layouts; common Badge, RecentSessionCard, VoiceReflectionView and LongitudinalTimeline; patient/supervisor stores; type contracts; unsupported messaging/recommendation screen notices; chatbot/04_chat_llm/chat_llm.py (optional context parameter, existing callers preserved). Local .env.local is ignored and not committed. Pre-existing intelligence_model modifications and other untracked work are unrelated to this integration.
