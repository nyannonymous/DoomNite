"""Live check against the DEPLOYED lobby directory (needs internet + the
Worker to be up). Same role as selftest_wsrelay_live.py: proves the real
HTTP round trip, not just a stub.

    python tools/selftest_lobby_live.py
"""
import time
import uuid

import lobby

PASS, FAIL = 0, 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name} {detail}")


room = f"selftest-{uuid.uuid4().hex[:8]}"
print(f"room: {room}  lobby base: {lobby.LOBBY_BASE}")

check("announce reaches the live Worker", lobby.announce(room, "Selftest Room", "doom", players=2))

rooms = lobby.list_rooms()
mine = next((r for r in rooms if r.get("room") == room), None)
check("the announced room shows up in list_rooms()", mine is not None, str(rooms))
if mine:
    check("the listed label matches what was announced", mine.get("label") == "Selftest Room", str(mine))
    check("the listed player count matches", mine.get("players") == 2, str(mine))

check("heartbeat reaches the live Worker", lobby.heartbeat(room))
rooms = lobby.list_rooms()
mine = next((r for r in rooms if r.get("room") == room), None)
check("a heartbeat with no label does not blank the room's label",
      mine is not None and mine.get("label") == "Selftest Room", str(mine))

check("remove reaches the live Worker", lobby.remove(room))
rooms = lobby.list_rooms()
check("the removed room is gone from the list",
      not any(r.get("room") == room for r in rooms), str(rooms))

# keep_announced(): the real background-thread helper mp_http.py uses.
# HEARTBEAT_INTERVAL is normally 20s (the thread only rechecks is_alive()
# once per interval, which is fine in production -- a closed room staying
# listed for up to ~20s is harmless against the Worker's 45s staleness
# window); shortened here so this test doesn't have to sleep that long.
lobby.HEARTBEAT_INTERVAL = 0.3
room2 = f"selftest-{uuid.uuid4().hex[:8]}"
alive_flag = {"v": True}
t = lobby.keep_announced(room2, "Thread Room", "doom", lambda: alive_flag["v"])
time.sleep(1.0)
rooms = lobby.list_rooms()
check("keep_announced's background thread announces the room",
      any(r.get("room") == room2 for r in rooms), str(rooms))

alive_flag["v"] = False
t.join(timeout=5.0)
rooms = lobby.list_rooms()
check("keep_announced removes the room once is_alive() goes false",
      not any(r.get("room") == room2 for r in rooms), str(rooms))

print(f"\n{PASS} passed, {FAIL} failed")
raise SystemExit(1 if FAIL else 0)
