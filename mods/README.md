# MDO mods
mdo-guard (/go, /hold) · mdo-heartbeat (/runs) · mdo-rules · mdo-morning (/morning) · mdo-tasks (/tasks, reads WORKLIST.md)
Run from disk: `claude --plugin-dir mods/mdo-guard --plugin-dir mods/mdo-heartbeat ...`
Set baseUrl / token in /config for heartbeat and morning. The token is stored as a sensitive setting, never in these files.
