# /sesh session spec — APP · DOOMNITE-PACK
- Mode: sesh (short task/queue session, ~15-60 min)
- Trigger: Hermes agent command hermes /sesh <project>
- Task: read TODO.md, execute next uncompleted item, write result back
- Persistence: update TODO.md; log to 
itesesh/runs/
- Auto-restart: yes (if crash during single task)
- Health: same as overnight but faster cycle (10s intervals)
