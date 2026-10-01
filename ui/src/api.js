// Talking to the Python server. Every call here is the same API the old
// single-file UI used, so nothing about the server had to change.

const j = async (r) => {
  if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
  return r.json();
};

export async function fetchEntries() {
  const d = await j(await fetch("/api/entries", { cache: "no-store" }));
  return d.entries || [];
}

export async function launchIndex(index) {
  return j(
    await fetch("/api/launch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Integer index only, by design. The server never accepts a path.
      body: JSON.stringify({ index }),
    })
  );
}

export async function dryrun(index) {
  return j(await fetch(`/api/dryrun?i=${index}`));
}

// Art filenames carry spaces and commas ("The Bikini Bottom Massacre 1,3.png"),
// so they must be percent-encoded or the server 404s.
export const artUrl = (name) => `/art/${encodeURIComponent(name)}`;

/**
 * Collapse the flat entry list into one group per game.
 *
 * Several launchers can share a display name (Brutal Doom on either IWAD), and
 * the server marks those with `group` + `variants`. They become a single tile
 * with a config picker rather than three near-identical cards.
 *
 * cfgs are sorted by the server's `index` so the order matches the console
 * menu. Sorting by mod count instead puts the plain build first and the HD
 * remaster second, which is backwards -- that bug shipped once already.
 */
export function groupEntries(entries) {
  const out = [];
  const byKey = new Map();
  for (const e of entries) {
    const key = e.group || e.label;
    let g = byKey.get(key);
    if (!g) {
      g = { key, label: key, note: e.note || "", kind: e.kind, cfgs: [], pick: 0 };
      byKey.set(key, g);
      out.push(g);
    }
    if (e.variants && e.variants.length) {
      // Reuse the server's variant list; it already carries the right indexes.
      if (!g.cfgs.length) {
        g.cfgs = e.variants
          .slice()
          .sort((a, b) => a.index - b.index)
          .map((v) => ({
            index: v.index,
            label: v.label,
            mods: v.mods || [],
            iwad: v.iwad,
            exists: v.exists,
            hd: !!v.hd,
          }));
      }
      g.kind = e.kind;
      g.note = e.note || g.note;
    } else {
      g.cfgs.push({
        index: entries.indexOf(e),
        label: e.variant || "default",
        mods: e.mods || [],
        iwad: e.iwad,
        exists: e.exists,
        exe: e.exe,
        wdir: e.wdir,
        hd: !!e.hd,
      });
    }
    if (e.art && !g.art) g.art = e.art;
    if (e.exists === false) g.missing = true;
  }
  for (const g of out) if (g.cfgs.every((c) => c.exists === false)) g.missing = true;
  return out;
}

export const FILTERS = [
  { id: "all", label: "All" },
  { id: "doom1", label: "Doom 1" },
  { id: "combo", label: "Combos" },
  { id: "variants", label: "Multi-config" },
  { id: "missing", label: "Missing files" },
];