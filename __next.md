# Next

Working notes. Newest items at the top.

---

## Protocol for fixing problems in third-party GitHub projects

We keep hitting the same class of problem: a change looks right in the diff but
the thing does not actually work at runtime. The protocol we should use:

1. **Read the surrounding code before editing.** Not just the lines that need
   changing — the caller, the config source, and whatever generates the file if
   it is generated.
2. **Separate "is it in the source?" from "does it run?"** A grep hit proves the
   text exists. It does not prove the code path is reachable, or that the
   generator was re-run, or that the change survived a rebuild.
3. **Prove it with real execution.** A `-norun` smoke test, an actual API call,
   a rendered page, a screenshot. Not "it compiles" and not "the diff looks
   right".
4. **Check what regenerates the artifact.** Half of our stale-reference bugs were
   files produced by a generator we edited but never re-ran.
5. **Verify the claim that motivated the change.** When a bug report says
   something happens twice, confirm the current behaviour before "fixing" it —
   and confirm the root cause is what we think rather than what is convenient.
6. **Commit source and generated artifacts together,** so a rebuild cannot
   reintroduce what was just removed.

---

## GRAND THEFT BAYOU

### Verify today's fixes actually work

Confirm each recent change is genuinely implemented and functioning at runtime,
per the protocol above. Do not accept a diff as proof.

### NPC population and behaviour

- Population needs to be **much higher** — in the range a GTA game would have.
- Behaviour should follow that same reference framework: pedestrians walking
  routes, traffic in lanes, ambient life that reacts rather than idling.

### City density — Chatboro / Orlearouge

These are **city centres** and currently read as sparse:

- **Dense building packing** — lots of skyscrapers and the kind of landmarks
  New Orleans would actually have.
- **Busy streets** with real infrastructure, not scattered props.
- Overall density needs to be **quite high**; this is the heart of the city.

### Metro / train system

The **train system is not implemented yet.** Needs building.

### Traffic lane discipline

- Cars currently drive **exactly down the middle of the road**. They need to
  drive **inside their respective lanes**.
- Road design needs to be concrete and logical.
- **No stray random roads with dead ends** — every road needs to **loop**, so
  cars do not simply stop.
