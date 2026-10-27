// Relais public en lecture seule : stats récentes d'un joueur (source : Tennis Abstract).
// GET ?players=Taylor Fritz,Alexander Zverev  -> { players: { "Taylor Fritz": {...} | null } }
// v3 : retour, classement, forme, surface, et qualité des adversaires (victoires pondérées, stats corrigées).
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "content-type",
};
const cache = new Map<string, { at: number; data: unknown }>();
const TTL = 6 * 3600 * 1000;

const strip = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "");
const slug = (name: string) => strip(name).replace(/[^A-Za-z]/g, "");

const num = (s: string) => {
  const v = parseFloat(s.replace("%", ""));
  return isFinite(v) ? v / 100 : null;
};

// Probabilité de gagner un jeu de service à partir de la proba de gagner un point
function holdFromPoint(p: number) {
  const q = 1 - p;
  const deuce = (20 * p ** 3 * q ** 3) * (p * p / (1 - 2 * p * q));
  return p ** 4 * (1 + 4 * q + 10 * q * q) + deuce;
}

// Victoire ou défaite, d'après la colonne du match (« X d. Y », « W », « L »)
function result(cell: string, surname: string): boolean | null {
  const t = strip(cell).replace(/\s+/g, " ").trim();
  if (/^W\b/.test(t)) return true;
  if (/^L\b/.test(t)) return false;
  const m = t.match(/^(.*?)\bd\.\s+(.*)$/);
  if (!m) return null;
  const left = m[1].toLowerCase(), right = m[2].toLowerCase(), s = surname.toLowerCase();
  if (!left.trim()) return true; // « d. Adversaire » = victoire
  if (left.includes(s)) return true;
  if (right.includes(s)) return false;
  return null;
}

type M = { date: string; surface: string; score: string; ace: number; spw: number; rpw: number | null; win: boolean | null; rank: number | null; opp: string | null; oppRank: number | null; set1: number | null };

// Nom de l'adversaire dans « X d. Y » (sans têtes de série ni pays)
function opponent(cell: string, win: boolean | null): string | null {
  const t = strip(cell).replace(/\s+/g, " ").trim();
  const m = t.match(/^(.*?)\bd\.\s+(.*)$/);
  if (!m || win === null) return null;
  const raw = (win ? m[2] : m[1]).replace(/\([^)]*\)/g, "").replace(/\[[^\]]*\]/g, "").trim();
  return raw || null;
}
// Chance de gagner d'après les classements (rang plus petit = plus fort)
const expWin = (rk: number, vrk: number) => 1 / (1 + Math.pow(rk / vrk, 0.8));
// Correction des stats selon la force de l'adversaire : servir face à un top 10 est plus dur que face à un 400e
const oppAdj = (vrk: number) => 0.015 * Math.log(Math.min(1000, Math.max(1, vrk)) / 100);

function parse(js: string, surname: string) {
  const body = js.slice(js.indexOf("<tbody>"), js.indexOf("</tbody>"));
  const rows = body.split("<tr>").slice(1);
  const out: M[] = [];
  for (const r of rows) {
    const cells = [...r.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((m) => m[1].replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").trim());
    if (cells.length < 15) continue;
    const [date, , surface, , rk, vrk, match, score, DR, A, , firstIn, firstWon, secondWon] = cells;
    const a = num(A), fi = num(firstIn), fw = num(firstWon), sw = num(secondWon);
    if (a === null || fi === null || fw === null || sw === null) continue;
    const spw = fi * fw + (1 - fi) * sw;
    const dr = parseFloat(DR);
    const rpw = isFinite(dr) && dr > 0 ? Math.min(0.75, Math.max(0.1, dr * (1 - spw))) : null; // DR = retour gagné / service perdu
    const rank = parseInt(rk, 10), oRank = parseInt(vrk, 10);
    const m = score.match(/^(\d+)-(\d+)/);
    const win = result(match, surname);
    out.push({ date, surface, score, ace: a, spw, rpw, win, rank: isFinite(rank) ? rank : null, opp: opponent(match, win), oppRank: isFinite(oRank) ? oRank : (vrk.trim() === "" ? null : 999), set1: m ? +m[1] + +m[2] : null });
    if (out.length >= 20) break;
  }
  return out;
}

const avg = (xs: number[]) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null);

async function player(name: string) {
  const key = slug(name);
  if (!key || key.length > 60) return null;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL) return hit.data;
  let data: unknown = null;
  try {
    const r = await fetch(`https://www.tennisabstract.com/jsfrags/${key}.js`, { headers: { "User-Agent": "Mozilla/5.0" } });
    if (r.ok) {
      const surname = strip(name.trim().split(/\s+/).pop() || "");
      const ms = parse(await r.text(), surname);
      if (ms.length >= 3) {
        const spw = avg(ms.map((m) => m.spw)) as number;
        const ace = avg(ms.map((m) => m.ace)) as number;
        const rp = ms.map((m) => m.rpw).filter((x): x is number => x !== null);
        const res = ms.map((m) => m.win).filter((x): x is boolean => x !== null);
        const s1 = ms.filter((m) => m.set1 !== null);
        // Stats corrigées selon le niveau de l'adversaire (adversaire non classé = 500e)
        const oR = (m: M) => m.oppRank ?? 500;
        const spwAdj = avg(ms.map((m) => m.spw - oppAdj(oR(m)))) as number;
        const rpwAdj = avg(ms.filter((m) => m.rpw !== null).map((m) => (m.rpw as number) - oppAdj(oR(m))));
        const surf: Record<string, { n: number; spw: number; rpw: number | null; spwAdj: number; rpwAdj: number | null; wins: number; known: number }> = {};
        for (const sname of [...new Set(ms.map((m) => m.surface).filter(Boolean))]) {
          const g = ms.filter((m) => m.surface === sname);
          const gr = g.map((m) => m.win).filter((x): x is boolean => x !== null);
          surf[sname] = {
            n: g.length,
            spw: avg(g.map((m) => m.spw)) as number,
            rpw: avg(g.map((m) => m.rpw).filter((x): x is number => x !== null)),
            spwAdj: avg(g.map((m) => m.spw - oppAdj(oR(m)))) as number,
            rpwAdj: avg(g.filter((m) => m.rpw !== null).map((m) => (m.rpw as number) - oppAdj(oR(m)))),
            wins: gr.filter(Boolean).length,
            known: gr.length,
          };
        }
        const rank = ms.find((m) => m.rank !== null)?.rank ?? null;
        // Qualité des résultats : victoires et défaites pondérées par le classement de l'adversaire
        const q = ms.filter((m) => m.win !== null);
        let sw = 0, sp = 0, expW = 0, i = 0;
        let vsBetterW = 0, vsBetterN = 0, top50W = 0, top50N = 0, weakW = 0, badL = 0;
        let best: { rank: number; name: string | null } | null = null;
        const oppRanks: number[] = [];
        for (const m of q) {
          const own = m.rank ?? rank ?? 300, vr = oR(m), e = expWin(own, vr), w = Math.pow(0.93, i++);
          sw += w; sp += w * ((m.win ? 1 : 0) - e); expW += e; oppRanks.push(vr);
          if (vr < own) { vsBetterN++; if (m.win) vsBetterW++; }
          if (vr <= 50) { top50N++; if (m.win) top50W++; }
          if (m.win && vr > Math.max(100, own * 1.5)) weakW++;
          if (!m.win && vr > own * 2 && vr > own + 20) badL++;
          if (m.win && (!best || vr < best.rank)) best = { rank: vr, name: m.opp };
        }
        oppRanks.sort((x, y) => x - y);
        const quality = q.length >= 5 ? {
          perf: sp / sw,                        // > 0 : gagne plus que son classement ne le prévoit, adversaires pris en compte
          expWins: expW, wins: q.filter((m) => m.win).length, n: q.length,
          vsBetter: { w: vsBetterW, n: vsBetterN },
          top50: { w: top50W, n: top50N },
          weakWins: weakW, badLosses: badL,
          medianOpp: oppRanks[Math.floor(oppRanks.length / 2)],
          bestWin: best,
        } : null;
        data = {
          matches: ms.length,
          lastDate: ms[0].date,
          lastSurface: ms[0].surface || null,
          spw,
          hold: holdFromPoint(spw),
          rpw: avg(rp),
          spwAdj,
          rpwAdj,
          quality,
          acePct: ace,
          acesPerServiceGame: ace * 6.3,
          rank,
          wins: res.filter(Boolean).length,
          results: res.length,
          winRate: res.length >= 5 ? res.filter(Boolean).length / res.length : null,
          form: ms.slice(0, 5).map((m) => (m.win === true ? "V" : m.win === false ? "D" : "?")).join(""),
          surf,
          set1Over95: s1.length ? s1.filter((m) => (m.set1 as number) >= 10).length / s1.length : null,
          set1Sample: s1.length,
        };
      }
    }
  } catch (_) { data = null; }
  cache.set(key, { at: Date.now(), data });
  return data;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  const url = new URL(req.url);
  const names = (url.searchParams.get("players") || "").split(",").map((s) => s.trim()).filter(Boolean).slice(0, 40);
  if (!names.length) {
    return new Response(JSON.stringify({ error: "Paramètre players manquant" }), { status: 400, headers: { ...CORS, "Content-Type": "application/json" } });
  }
  const res: Record<string, unknown> = {};
  for (let i = 0; i < names.length; i += 6) {
    const part = names.slice(i, i + 6);
    const got = await Promise.all(part.map(player));
    part.forEach((n, j) => (res[n] = got[j]));
  }
  return new Response(JSON.stringify({ source: "tennisabstract.com", version: 3, players: res }), {
    headers: { ...CORS, "Content-Type": "application/json", "Cache-Control": "public, max-age=1800" },
  });
});
