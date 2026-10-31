# /nitesesh overnight spec — APP · DOOMNITE-PACK
- Mode: overnight (/nitesesh)
- Entry: see parent repo start.sh, package.json, main.py, or start_tupac.py
- Auto-restart: yes (on crash / health-fail / timeout)
- Health check: HTTP /health or file-based (see ctl.sh or start-server.bat)
- Session log: this file + overnight-run.log
- Duration target: 8+ hours (overnight)
- Exit conditions: fatal syntax error, missing dependency, port conflict, health failure 3x in a row
- Session persistence: load last 
itesesh/runs/*.md before start if exists
