# Production convergence audit

This audit starts at the production build (`VITE_DATA_SOURCE=api`) and follows only code that a signed-in user can reach. A file existing in the repository is not evidence that a production capability is connected.

## Chosen product surface

The supported shell is the production inbox in `pages/inbox.tsx`: OA identity, mailbox-scoped data, inbox, leads, replies and outreach all converge there. Its visual direction is **Paper & Ink with Mineral accents** from the design studies: warm reading surfaces, dense but quiet hierarchy, dark mineral green for product identity, and an optional evidence panel on the right.

The former `RealMailbox` is not a second product. Useful behavior must migrate to the supported shell, then the pilot is removed.

## Reachability matrix

| Capability | Production UI | Production API | Status after convergence pass |
| --- | --- | --- | --- |
| OA identity and mailbox permissions | Supported inbox | `/api/mailboxes`, mailbox-scoped headers | Connected |
| Larry sees Sales + Larry | Mailbox selector | `_mailbox_row` access policy | Connected |
| Other users see only themselves | Mailbox selector | `_mailbox_row` access policy | Connected |
| IMAP sync | Sidebar action + polling | `/api/sync` | Connected |
| Per-message AI reading | Inline evidence card | ingest reader + `/api/threads/{id}/analyze` | Connected; model configuration required |
| Cross-topic AI reading | Hidden right panel | `/api/assistant` | Connected; model configuration required |
| AI citations | Right panel links to source thread | checked quote/source IDs | Connected |
| AI audit and clear-display | Right panel | append-only mailbox-scoped events | Connected |
| Lead suggestions and confirmation | Leads page | `/api/leads/*` | Connected; model configuration required for new suggestions |
| Reply drafting | Reply composer when task permits | `/api/threads/{id}/draft` | Connected; current mailbox policy may hide it |
| SMTP reply | Reply composer | one-time send token + SMTP | Connected |
| Approved outreach sequence | `/outreach` | `/api/prospects/*` | Connected; global send switch remains independent |
| Attachment text | Attachment sheet | `/api/attachments/{id}/text` | Connected |
| Body translation | Former pilot only | former `/mail/messages/{id}/translate` | Not yet migrated |
| Automatic structured fact strip | Former pilot only | former extraction queue | Not yet migrated |
| Per-message jump from an AI citation | Thread-level navigation | source thread and message IDs exist | Thread connected; exact message focus remains |

## Duplicate or non-production implementations

### `components/real-mailbox.tsx`

Earlier real-mail pilot. It contains useful interaction ideas, but uses `/__localmail` and is redirected away in production. It must be deleted after translation and structured extraction migrate.

### `components/real-mailbox-ask.tsx`

Earlier right-side assistant tied to the loopback pilot. Its checked-citation behavior has moved to the supported production shell. Do not add new behavior here.

### `components/mailbox-assistant.tsx`

Design-only assistant using fixtures and keyword matching. It remains only as a visual study under `/design`; it must never be presented as real AI.

### `server/local_web.py`

Loopback-only pilot service with its own job state, assistant audit, analysis, translation and extraction endpoints. It is not mounted by the production server. Remaining production-worthy capabilities must migrate to `api/app.py`; then this service and its dedicated UI can be removed.

## Configuration breaks

Production currently has no `LLM_BACKEND`, model route, gateway URL or model API key. Mail continues to ingest correctly, but readings, assistant answers, translations, lead extraction and drafts cannot run. The UI must expose this state and must not fabricate placeholder output.

The supported model contract remains:

- local/OpenAI-compatible: `DGX_GATEWAY_URL`, `DGX_API_KEY`, `LOCAL_MODEL`;
- Anthropic: `LLM_BACKEND=claude`, `ANTHROPIC_API_KEY`, `MODEL`.

Model selection is an operations decision gated by real-mail evaluation; it is not hard-coded in the interface.

## Removal gate

Do not delete pilot or design code until all of the following are true:

1. production translation and structured extraction are migrated or explicitly rejected;
2. exact-message citation navigation works;
3. OA mailbox isolation tests cover every new endpoint;
4. production visual regression captures exist for desktop, assistant-open, dark and mobile states;
5. the production model route passes the repository eval suites on representative, non-committed mail samples.
