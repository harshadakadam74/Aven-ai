# API reference (Stage 1)

Base URL: `http://127.0.0.1:8000`. Every `/api/v1` route requires the header `X-Aven-Key: <AVEN_AI_API_KEY>`. Errors use FastAPI's `{"detail": "..."}` shape.

**Status:** written, not run (FastAPI could not be installed when this was built). Request validation is covered by schema tests.

| Method and path | Purpose |
|---|---|
| `GET /health` | No auth. `{"status","version","schema_version"}` |
| `POST /api/v1/chat` | Body `{"message": str (1-2000), "conversation_id"?: str, "private"?: bool}`. Returns `text, intent, conversation_id, language, needs_input, stop_speaking, data`. Rate limited (default 60/min per client). |
| `GET /api/v1/conversations/{id}/messages?limit=50` | Saved messages |
| `DELETE /api/v1/conversations` | Delete all saved history; returns `{"deleted_conversations": n}` only after verifying nothing remains |
| `GET /api/v1/notes`, `POST /api/v1/notes` | `{"text": str}` |
| `GET /api/v1/tasks?include_done=false`, `POST /api/v1/tasks`, `POST /api/v1/tasks/{id}/complete` | `{"title": str}` |
| `GET /api/v1/reminders?status=pending` | `pending`, `fired` or `cancelled` |

Unknown JSON fields are rejected (HTTP 422). `needs_input` is `"clarification"` or `"confirmation"` when Aven is waiting for your answer in the same conversation.

Opening apps is deliberately unavailable through this API.

## Example (PowerShell)

```powershell
$h = @{ "X-Aven-Key" = $env:AVEN_AI_API_KEY }
$body = @{ message = "remind me to study at seven" } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/chat -Headers $h -ContentType "application/json" -Body $body
$r.text            # "Do you mean 7:00 AM or 7:00 PM?"
$body = @{ message = "pm"; conversation_id = $r.conversation_id } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/chat -Headers $h -ContentType "application/json" -Body $body
```

Later stages add voice, settings, memory and action-preview endpoints from the master prompt.
