// Relais public en lecture seule : stats récentes d'un joueur (source : Tennis Abstract).
// GET ?players=Taylor Fritz,Alexander Zverev&h2h=Taylor Fritz|Alexander Zverev
//   -> { players: { "Taylor Fritz": {...} | null }, h2h: { "Taylor Fritz|Alexander Zverev": {...} } }
// v5 : Elo par surface, fatigue, mental (balles de break, tie-breaks, sets décisifs), détail du service,
//      niveau des tournois, tendance, main (gaucher/droitier), face-à-face.
// v8 : stats de la saison en cours pour les calculs (career.season).
// v7 : toute la carrière (saisons circuit + Challengers, surfaces) ; jeux du 1er set des derniers matchs.
// v6 : lit aussi les autres tableaux de la page Tennis Abstract : bilans sur 52 semaines (surface, niveau,
//      contre gauchers/droitiers), face-à-face de toute la carrière, vitesse de service (mph).
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "content-type",
};
const TTL = 6 * 3600 * 1000;
const UA = { headers: { "User-Agent": "Mozilla/5.0" } };
const DAY = 86400000;

const strip = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "");
const slug = (name: string) => strip(name).replace(/[^A-Za-z]/g, "");
const norm = (name: string) => strip(name).toLowerCase().replace(/[^a-z]/g, "");

const pctNum = (s: string) => {
  const v = parseFloat((s || "").replace("%", ""));
  return isFinite(v) ? v / 100 : null;
};
const avg = (xs: number[]) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null);
const nums = (xs: (number | null)[]) => xs.filter((x): x is number => x !== null);

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

const MON: Record<string, number> = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };
function parseDate(s: string): number | null {
  let m = s.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{4})/);
  if (m && MON[m[2].toLowerCase()] !== undefined) return Date.UTC(+m[3], MON[m[2].toLowerCase()], +m[1]);
  m = s.match(/^(\d{4})-?(\d{2})-?(\d{2})/);
  if (m) return Date.UTC(+m[1], +m[2] - 1, +m[3]);
  return null;
}
const minutes = (s: string) => {
  const m = (s || "").match(/^(\d+):(\d{2})$/);
  return m ? +m[1] * 60 + +m[2] : null;
};
// Niveau du tournoi d'après son nom (approximatif)
function level(name: string): "top" | "tour" | "low" {
  const n = strip(name).toLowerCase();
  if (/australian open|roland garros|french open|wimbledon|us open|masters|finals|indian wells|miami|monte carlo|madrid|\brome\b|\broma\b|canada|montreal|toronto|cincinnati|shanghai|paris|beijing|doha|dubai|wuhan/.test(n)) return "top";
  if (/\bch\b|challenger|\bitf\b|^[mw]\d{2,3}\b|futures|\b125\b/.test(n)) return "low";
  return "tour";
}
// Score du point de vue du joueur : sets, tie-breaks, set décisif, premier set
function scoreInfo(score: string, win: boolean | null) {
  if (win === null || /RET|W\/O|DEF|ABD|ABN/i.test(score)) return null;
  const sets = score.split(/\s+/).map((t) => t.match(/^(\d+)-(\d+)/)).filter(Boolean).map((m) => [+m![1], +m![2]]);
  if (!sets.length) return null;
  const own = (s: number[]) => (win ? s[0] > s[1] : s[1] > s[0]); // le score est écrit du point de vue du vainqueur
  const winnerSets = sets.filter((s) => s[0] > s[1]).length;
  const decider = (winnerSets === 2 && sets.length === 3) || (winnerSets === 3 && sets.length === 5);
  const tbs = sets.filter((s) => (s[0] === 7 && s[1] === 6) || (s[0] === 6 && s[1] === 7));
  return { tbN: tbs.length, tbW: tbs.filter(own).length, decider, firstLost: !own(sets[0]) };
}

type M = {
  date: string; d: number | null; tourney: string; lvl: string; surface: string; score: string;
  ace: number; df: number | null; fi: number; fw: number; sw: number; spw: number; rpw: number | null;
  bps: number | null; bpf: number | null; mins: number | null;
  win: boolean | null; rank: number | null; opp: string | null; oppRank: number | null; set1: number | null;
};

function parse(js: string, surname: string) {
  const body = js.slice(js.indexOf("<tbody>"), js.indexOf("</tbody>"));
  const rows = body.split("<tr>").slice(1);
  const out: M[] = [];
  for (const r of rows) {
    const cells = [...r.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((m) => m[1].replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").trim());
    if (cells.length < 15) continue;
    const [date, tourney, surface, , rk, vrk, match, score, DR, A, DF, firstIn, firstWon, secondWon, BP, time] = cells;
    const a = pctNum(A), fi = pctNum(firstIn), fw = pctNum(firstWon), sw = pctNum(secondWon);
    if (a === null || fi === null || fw === null || sw === null) continue;
    const spw = fi * fw + (1 - fi) * sw;
    const dr = parseFloat(DR);
    const rpw = isFinite(dr) && dr > 0 ? Math.min(0.75, Math.max(0.1, dr * (1 - spw))) : null; // DR = retour gagné / service perdu
    const rank = parseInt(rk, 10), oRank = parseInt(vrk, 10);
    const m = score.match(/^(\d+)-(\d+)/);
    const bp = (BP || "").match(/^(\d+)\/(\d+)$/);
    const win = result(match, surname);
    out.push({
      date, d: parseDate(date), tourney, lvl: level(tourney), surface, score,
      ace: a, df: pctNum(DF), fi, fw, sw, spw, rpw,
      bps: bp ? +bp[1] : null, bpf: bp ? +bp[2] : null, mins: minutes(time || ""),
      win, rank: isFinite(rank) ? rank : null, opp: opponent(match, win),
      oppRank: isFinite(oRank) ? oRank : (vrk.trim() === "" ? null : 999), set1: m ? +m[1] + +m[2] : null,
    });
    if (out.length >= 150) break;
  }
  return out;
}

// ---------- Autres tableaux de la page joueur (repérés par leur id)
function table(js: string, id: string) {
  const t = js.replace(/\\"/g, '"');
  const i = t.indexOf(`id="${id}"`);
  if (i < 0) return null;
  const end = t.indexOf("</table>", i);
  const chunk = t.slice(i, end < 0 ? undefined : end);
  const clean = (h: string) => h.replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();
  const head = [...(chunk.match(/<thead>([\s\S]*?)<\/thead>/)?.[1] || "").matchAll(/<th[^>]*>([\s\S]*?)<\/th>/g)].map((m) => clean(m[1]));
  const body = chunk.slice(chunk.indexOf("<tbody>"));
  const rows = body.split(/<tr[^>]*>/).slice(1).map((r) => [...r.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((m) => clean(m[1]))).filter((r) => r.length);
  return { head, rows };
}
const num = (s: string | undefined) => { const v = parseFloat((s || "").replace("%", "")); return isFinite(v) ? v : null; };
const wl = (s: string | undefined) => { const m = (s || "").match(/^(\d+)-(\d+)$/); return m ? [+m[1], +m[2]] : null; };

// Bilans sur 52 semaines : une ligne par split (Hard, Clay, Grass, Grand Slams, Masters, vs Lefties…)
function splits52(js: string) {
  const t = table(js, "last52-splits");
  if (!t) return null;
  const col = (name: string) => t.head.indexOf(name);
  const out: Record<string, Record<string, number | null>> = {};
  for (const r of t.rows) {
    const g = (name: string) => { const i = col(name); return i < 0 ? undefined : r[i]; };
    const pct = (name: string) => { const v = num(g(name)); return v === null ? null : v / 100; };
    const tb = wl(g("TB W-L"));
    out[r[0]] = {
      m: num(g("M")), w: num(g("W")), l: num(g("L")), tbW: tb ? tb[0] : null, tbN: tb ? tb[0] + tb[1] : null,
      hold: pct("Hld%"), brk: pct("Brk%"), ace: pct("A%"), df: pct("DF%"), firstIn: pct("1stIn"),
      firstWon: pct("1st%"), secondWon: pct("2nd%"), spw: pct("SPW"), rpw: pct("RPW"),
    };
  }
  return out;
}
// Face-à-face de toute la carrière : adversaire -> victoires, défaites, tie-breaks, dates
function careerH2h(js: string) {
  const t = table(js, "head-to-heads");
  if (!t) return {};
  const out: Record<string, { w: number; l: number; tbW: number | null; tbN: number | null; first: string; last: string }> = {};
  for (const r of t.rows) {
    const name = (r[1] || "").replace(/\[[^\]]*\]/g, "").trim();
    if (!name) continue;
    out[norm(name)] = { w: num(r[2]) || 0, l: num(r[3]) || 0, tbW: num(r[6]), tbN: num(r[5]), first: r[9] || "", last: r[10] || "" };
  }
  return out;
}
// Vitesse de service (mph) : moyenne des matchs mesurés les plus récents
function serveSpeed(js: string) {
  const t = table(js, "serve-speed");
  if (!t || !t.rows.length) return null;
  const col = (name: string) => t.head.indexOf(name);
  // la ligne « Career (N matches) » est un total : on ne garde que les matchs
  const rows = t.rows.filter((r) => !/^career/i.test(r[0] || "")).slice(0, 12);
  if (!rows.length) return null;
  const av = (name: string) => { const i = col(name); const v = rows.map((r) => num(r[i])).filter((x): x is number => x !== null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const mx = (name: string) => { const i = col(name); const v = rows.map((r) => num(r[i])).filter((x): x is number => x !== null); return v.length ? Math.max(...v) : null; };
  return { n: rows.length, avg: av("Avg Speed"), first: av("1st Avg"), second: av("2nd Avg"), max: mx("Max 1st"), latest: rows[0][0] || null, oldest: rows[rows.length - 1][0] || null };
}

// ---------- Toute la carrière : saisons (circuit + Challengers) et surfaces
// Testé sur 43 000 matchs ATP (model/career_eval.py) : saisons pondérées avec une demi-vie de 1 an,
// 300 points d'a priori, écart de surface de la carrière réduit selon le nombre de matchs (k = 30).
const HALF_LIFE = 1, PRIOR_PTS = 300, K_SURF = 30, PTS_PER_MATCH = 80, CHALL_ADJ = 0.018;
function careerStats(js: string, wta: boolean) {
  const avgS = wta ? 0.56 : 0.64;
  const now = new Date(), t = now.getUTCFullYear() + (now.getTime() - Date.UTC(now.getUTCFullYear(), 0, 1)) / (365 * DAY);
  const years: Record<string, unknown>[] = [];
  let sw = 0, sv = 0, rw = 0, rv = 0, aw = 0, games = 0, sets = 0, tbs = 0, hw = 0, bw = 0, wsum = 0, m = 0, msAll = 0;
  // Saison en cours seulement (utilisée pour les calculs)
  const S = { sw: 0, sv: 0, rw: 0, aw: 0, hw: 0, bw: 0, w: 0, games: 0, sets: 0, tbs: 0, m: 0, ms: 0 };
  for (const [id, lvl] of [["tour-years", "tour"], ["chall-years", "chall"]] as const) {
    const tb = table(js, id);
    if (!tb) continue;
    const col = (name: string) => tb.head.indexOf(name);
    for (const r of tb.rows) {
      const y = parseInt(r[0], 10);
      if (!isFinite(y)) continue;
      const g = (name: string) => { const i = col(name); return i < 0 ? undefined : r[i]; };
      const pct = (name: string) => { const v = num(g(name)); return v === null ? null : v / 100; };
      const M = num(g("M")) || 0, MS = num(g("MS")) || 0, spw = pct("SPW"), rpw = pct("RPW"), ace = pct("A%");
      const st = wl(g("Set W-L")), gm = wl(g("Game W-L")), tbx = wl(g("TB W-L")), hold = pct("Hld%"), brk = pct("Brk%");
      const adj = lvl === "chall" ? CHALL_ADJ : 0; // stats plus faciles face à des adversaires plus faibles
      const age = y === Math.floor(t) ? (t - y) / 2 : t - (y + 0.5);
      const w = Math.pow(0.5, Math.max(0, age) / HALF_LIFE);
      m += M; msAll += MS;
      if (y === Math.floor(t)) {
        S.m += M; S.ms += MS;
        if (MS > 0 && spw !== null && rpw !== null) {
          const pts = MS * PTS_PER_MATCH;
          S.sw += pts * (spw - adj); S.sv += pts; S.rw += pts * (rpw - adj); if (ace !== null) S.aw += pts * ace;
          if (hold !== null && brk !== null) { S.hw += MS * hold; S.bw += MS * brk; S.w += MS; }
        }
        if (st && gm) { S.games += gm[0] + gm[1]; S.sets += st[0] + st[1]; if (tbx) S.tbs += tbx[0] + tbx[1]; }
      }
      if (MS > 0 && spw !== null && rpw !== null) {
        const pts = MS * PTS_PER_MATCH * w;
        sw += pts * (spw - adj); sv += pts; rw += pts * (rpw - adj); rv += pts;
        if (ace !== null) aw += pts * ace;
        if (hold !== null && brk !== null) { hw += MS * w * hold; bw += MS * w * brk; wsum += MS * w; }
      }
      if (st && gm && st[0] + st[1] > 0) { games += w * (gm[0] + gm[1]); sets += w * (st[0] + st[1]); if (tbx) tbs += w * (tbx[0] + tbx[1]); }
      years.push({ y, lvl, m: M, ms: MS, spw, rpw, hold, brk, ace, gps: st && gm && st[0] + st[1] > 0 ? (gm[0] + gm[1]) / (st[0] + st[1]) : null,
                   tbps: st && tbx && st[0] + st[1] > 0 ? (tbx[0] + tbx[1]) / (st[0] + st[1]) : null });
    }
  }
  if (!sv) return null;
  // Saison en cours : 600 points d'a priori vers la moyenne du circuit (testé sur 2024-2026, model/season_eval.py)
  const SP = 600;
  const season = {
    year: Math.floor(t), matches: S.m, withStats: S.ms,
    spw: (S.sw + SP * avgS) / (S.sv + SP), rpw: (S.rw + SP * (1 - avgS)) / (S.sv + SP),
    ace: (S.aw + SP * (wta ? 0.035 : 0.07)) / (S.sv + SP),
    hold: S.w ? S.hw / S.w : null, brk: S.w ? S.bw / S.w : null,
    gps: S.sets ? S.games / S.sets : null, tbps: S.sets ? S.tbs / S.sets : null,
  };
  // Surfaces sur toute la carrière (circuit principal)
  const cs = table(js, "career-splits");
  const surf: Record<string, Record<string, number | null>> = {};
  if (cs) {
    const col = (name: string) => cs.head.indexOf(name);
    const rowsS = cs.rows.filter((r) => ["Hard", "Clay", "Grass"].includes(r[0]));
    const val = (r: string[], name: string) => { const v = num(r[col(name)]); return v === null ? null : v / 100; };
    let a = 0, b = 0, n = 0;
    for (const r of rowsS) { const MS = num(r[col("MS")]) || 0, s = val(r, "SPW"), q = val(r, "RPW"); if (MS && s !== null && q !== null) { a += MS * s; b += MS * q; n += MS; } }
    if (n) for (const r of rowsS) {
      const M = num(r[col("M")]) || 0, MS = num(r[col("MS")]) || 0, s = val(r, "SPW"), q = val(r, "RPW");
      if (!MS || s === null || q === null) continue;
      const k = M / (M + K_SURF);
      surf[r[0]] = { m: M, dspw: (s - a / n) * k, drpw: (q - b / n) * k, spwRaw: s, rpwRaw: q, hold: val(r, "Hld%") };
    }
  }
  years.sort((x, y) => (y.y as number) - (x.y as number));
  return {
    spw: (sw + PRIOR_PTS * avgS) / (sv + PRIOR_PTS), rpw: (rw + PRIOR_PTS * (1 - avgS)) / (rv + PRIOR_PTS),
    ace: (aw + PRIOR_PTS * (wta ? 0.035 : 0.07)) / (sv + PRIOR_PTS),
    hold: wsum ? hw / wsum : null, brk: wsum ? bw / wsum : null,
    gps: sets ? (games + 5 * 9.6) / (sets + 5) : null, tbps: sets ? (tbs + 5 * 0.2) / (sets + 5) : null,
    season, matches: m, withStats: msAll, seasons: new Set(years.map((x) => x.y)).size, years: years.slice(0, 12), surf,
  };
}

// ---------- Elo (Tennis Abstract publie une page par circuit)
type Elo = { tour: string; elo: number | null; hElo: number | null; cElo: number | null; gElo: number | null; eloRank: number | null; age: number | null };
let eloCache: { at: number; map: Map<string, Elo> } | null = null;
function parseElo(html: string, tour: string, map: Map<string, Elo>) {
  const rows = html.split(/<tr[^>]*>/i).slice(1);
  let idx: Record<string, number> | null = null;
  for (const r of rows) {
    const cells = [...r.matchAll(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi)].map((m) => m[1].replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").trim());
    if (!idx) {
      if (cells.some((c) => /^player$/i.test(c))) {
        idx = {};
        cells.forEach((c, i) => { const k = c.toLowerCase().replace(/\s/g, ""); if (idx && !(k in idx)) idx[k] = i; });
      }
      continue;
    }
    const name = cells[idx.player];
    if (!name) continue;
    const n = (k: string) => { const i = idx![k]; if (i === undefined) return null; const v = parseFloat(cells[i]); return isFinite(v) ? v : null; };
    map.set(norm(name), { tour, elo: n("elo"), hElo: n("helo"), cElo: n("celo"), gElo: n("gelo"), eloRank: n("elorank") ?? n("rank"), age: n("age") });
  }
}
async function elos() {
  if (eloCache && Date.now() - eloCache.at < TTL) return eloCache.map;
  const map = new Map<string, Elo>();
  for (const tour of ["atp", "wta"]) {
    try {
      const r = await fetch(`https://tennisabstract.com/reports/${tour}_elo_ratings.html`, UA);
      if (r.ok) parseElo(await r.text(), tour, map);
    } catch (_) { /* page indisponible : pas d'Elo */ }
  }
  eloCache = { at: Date.now(), map };
  return map;
}

// ---------- Main, revers, âge, taille (page joueur)
async function bio(key: string, tour: string) {
  try {
    const r = await fetch(`https://www.tennisabstract.com/cgi-bin/${tour === "wta" ? "w" : ""}player-classic.cgi?p=${key}`, UA);
    if (!r.ok) return null;
    const t = await r.text();
    const g = (re: RegExp) => { const m = t.match(re); return m ? m[1] : null; };
    const hand = g(/var\s+hand\s*=\s*['"]([LRU])['"]/);
    const bh = g(/var\s+backhand\s*=\s*['"]?(\d)/);
    const dob = g(/var\s+dob\s*=\s*['"]?(\d{8})/);
    const ht = g(/var\s+ht\s*=\s*['"]?(\d{3})/);
    if (!hand && !dob && !ht) return null;
    const born = dob ? Date.UTC(+dob.slice(0, 4), +dob.slice(4, 6) - 1, +dob.slice(6, 8)) : null;
    return { hand, backhand: bh ? +bh : null, age: born ? (Date.now() - born) / (365.25 * DAY) : null, height: ht ? +ht : null };
  } catch (_) { return null; }
}

// ---------- Joueur
const cache = new Map<string, { at: number; data: unknown; rows: M[]; h2h: Record<string, { w: number; l: number; tbW: number | null; tbN: number | null; first: string; last: string }> }>();
async function player(name: string) {
  const key = slug(name);
  if (!key || key.length > 60) return null;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < TTL) return hit;
  let data: unknown = null, all: M[] = [], h2hMap: Record<string, { w: number; l: number; tbW: number | null; tbN: number | null; first: string; last: string }> = {};
  try {
    const eloMap = await elos();
    const elo = eloMap.get(norm(name)) || null;
    const [r, b] = await Promise.all([
      fetch(`https://www.tennisabstract.com/jsfrags/${key}.js`, UA),
      bio(key, elo ? elo.tour : "atp"),
    ]);
    if (r.ok) {
      const surname = strip(name.trim().split(/\s+/).pop() || "");
      const js = await r.text();
      all = parse(js, surname);
      const sp52 = splits52(js);
      h2hMap = careerH2h(js);
      const speed = serveSpeed(js);
      const car = careerStats(js, !!elo && /wta/i.test(elo.tour));
      const ms = all.slice(0, 20); // forme et stats globales : 20 derniers matchs
      const s60 = all.slice(0, 60); // surface, mental, service, niveaux : 60 derniers
      if (ms.length >= 3) {
        const spw = avg(ms.map((m) => m.spw)) as number;
        const ace = avg(ms.map((m) => m.ace)) as number;
        const res = ms.map((m) => m.win).filter((x): x is boolean => x !== null);
        const s1 = ms.filter((m) => m.set1 !== null);
        const oR = (m: M) => m.oppRank ?? 500; // adversaire non classé = 500e
        const spwAdj = avg(ms.map((m) => m.spw - oppAdj(oR(m)))) as number;
        const rpwAdj = avg(ms.filter((m) => m.rpw !== null).map((m) => (m.rpw as number) - oppAdj(oR(m))));

        // Par surface
        const surf: Record<string, Record<string, unknown>> = {};
        for (const sname of [...new Set(s60.map((m) => m.surface).filter(Boolean))]) {
          const g = s60.filter((m) => m.surface === sname);
          const g1 = g.filter((m) => m.set1 !== null);
          const gspw = avg(g.map((m) => m.spw)) as number;
          const gr = g.map((m) => m.win).filter((x): x is boolean => x !== null);
          surf[sname] = {
            n: g.length, spw: gspw, hold: holdFromPoint(gspw),
            acesPerServiceGame: (avg(g.map((m) => m.ace)) as number) * 6.3,
            set1Over95: g1.length ? g1.filter((m) => (m.set1 as number) >= 10).length / g1.length : null,
            lastDate: g[0].date,
            rpw: avg(nums(g.map((m) => m.rpw))),
            spwAdj: avg(g.map((m) => m.spw - oppAdj(oR(m)))) as number,
            rpwAdj: avg(g.filter((m) => m.rpw !== null).map((m) => (m.rpw as number) - oppAdj(oR(m)))),
            wins: gr.filter(Boolean).length, known: gr.length,
          };
        }

        // Bilans 52 semaines par surface (tous les matchs de l'année) : remplacent le calcul sur les derniers matchs
        if (sp52) {
          const offS = spwAdj - spw, offR = rpwAdj !== null ? rpwAdj - (avg(nums(ms.map((m) => m.rpw))) ?? rpwAdj) : 0;
          for (const sname of ["Hard", "Clay", "Grass"]) {
            const x = sp52[sname];
            if (!x || !x.m || x.m < 3 || x.spw === null) continue;
            const prev = surf[sname] || {};
            surf[sname] = {
              ...prev, n: x.m, spw: x.spw, hold: x.hold ?? holdFromPoint(x.spw), rpw: x.rpw,
              spwAdj: x.spw + offS, rpwAdj: x.rpw !== null ? x.rpw + offR : prev.rpwAdj ?? null,
              acesPerServiceGame: x.ace !== null ? x.ace * 6.3 : prev.acesPerServiceGame ?? null,
              wins: x.w, known: x.m, tbW: x.tbW, tbN: x.tbN, src: "52 semaines",
            };
          }
        }

        // Qualité des résultats : victoires pondérées par le classement de l'adversaire
        const rank = ms.find((m) => m.rank !== null)?.rank ?? null;
        const q = ms.filter((m) => m.win !== null);
        let sw = 0, sp = 0, expW = 0, i = 0;
        let vsBetterW = 0, vsBetterN = 0, top50W = 0, top50N = 0, weakW = 0, badL = 0;
        let best: { rank: number; name: string | null } | null = null;
        const oppRanks: number[] = [], resid: number[] = [];
        for (const m of q) {
          const own = m.rank ?? rank ?? 300, vr = oR(m), e = expWin(own, vr), w = Math.pow(0.93, i++);
          const rs = (m.win ? 1 : 0) - e;
          sw += w; sp += w * rs; expW += e; oppRanks.push(vr); resid.push(rs);
          if (vr < own) { vsBetterN++; if (m.win) vsBetterW++; }
          if (vr <= 50) { top50N++; if (m.win) top50W++; }
          if (m.win && vr > Math.max(100, own * 1.5)) weakW++;
          if (!m.win && vr > own * 2 && vr > own + 20) badL++;
          if (m.win && (!best || vr < best.rank)) best = { rank: vr, name: m.opp };
        }
        oppRanks.sort((x, y) => x - y);
        const quality = q.length >= 5 ? {
          perf: sp / sw, // > 0 : gagne plus que son classement ne le prévoit, adversaires pris en compte
          expWins: expW, wins: q.filter((m) => m.win).length, n: q.length,
          vsBetter: { w: vsBetterW, n: vsBetterN }, top50: { w: top50W, n: top50N },
          weakWins: weakW, badLosses: badL,
          medianOpp: oppRanks[Math.floor(oppRanks.length / 2)], bestWin: best,
          perf5: avg(resid.slice(0, 5)), perf20: avg(resid), // tendance
        } : null;

        // Fatigue et inactivité (dates = début du tournoi chez Tennis Abstract)
        const now = Date.now(), d0 = ms[0].d;
        const rec = ms.filter((m) => m.d !== null && now - (m.d as number) <= 14 * DAY);
        const fatigue = {
          days: d0 !== null ? Math.max(0, Math.round((now - d0) / DAY)) : null,
          n14: rec.length,
          min14: rec.some((m) => m.mins !== null) ? nums(rec.map((m) => m.mins)).reduce((s, x) => s + x, 0) : null,
          lastMin: ms[0].mins,
        };

        // Mental : balles de break, tie-breaks, sets décisifs, remontées
        let bps = 0, bpf = 0, tbW = 0, tbN = 0, decW = 0, decN = 0, cbW = 0, cbN = 0;
        for (const m of s60) {
          if (m.bps !== null && m.bpf !== null) { bps += m.bps; bpf += m.bpf; }
          const si = scoreInfo(m.score, m.win);
          if (!si) continue;
          tbW += si.tbW; tbN += si.tbN;
          if (si.decider) { decN++; if (m.win) decW++; }
          if (si.firstLost) { cbN++; if (m.win) cbW++; }
        }
        // tie-breaks : bilan 52 semaines (toutes surfaces) s'il est plus fourni
        if (sp52) {
          const t = ["Hard", "Clay", "Grass"].map((k) => sp52[k]).filter((x) => x && x.tbN !== null);
          const n52 = t.reduce((a, x) => a + (x!.tbN as number), 0);
          if (n52 > tbN) { tbN = n52; tbW = t.reduce((a, x) => a + (x!.tbW as number), 0); }
        }
        const clutch = { bpSaved: bps, bpFaced: bpf, tbW, tbN, decW, decN, comebackW: cbW, comebackN: cbN };

        // Détail du service
        const serve = {
          firstIn: avg(s60.map((m) => m.fi)), firstWon: avg(s60.map((m) => m.fw)),
          secondWon: avg(s60.map((m) => m.sw)), df: avg(nums(s60.map((m) => m.df))),
        };

        // Résultats par niveau de tournoi
        const levels: Record<string, { w: number; n: number }> = { top: { w: 0, n: 0 }, tour: { w: 0, n: 0 }, low: { w: 0, n: 0 } };
        for (const m of s60) if (m.win !== null) { levels[m.lvl].n++; if (m.win) levels[m.lvl].w++; }
        if (sp52) { // 52 semaines : plus de matchs
          const add = (k: string, keys: string[]) => {
            const xs = keys.map((x) => sp52[x]).filter((x) => x && x.m);
            const n = xs.reduce((a, x) => a + (x!.m as number), 0);
            if (n > levels[k].n) levels[k] = { w: xs.reduce((a, x) => a + (x!.w as number), 0), n };
          };
          add("top", ["Grand Slams", "Masters"]); add("tour", ["Other Tours"]); add("low", ["Challengers", "ITFs"]);
        }
        const hands = sp52 ? {
          vsLefty: sp52["vs Lefties"] ? { w: sp52["vs Lefties"].w, n: sp52["vs Lefties"].m } : null,
          vsRighty: sp52["vs Righties"] ? { w: sp52["vs Righties"].w, n: sp52["vs Righties"].m } : null,
          vsTop10: sp52["vs Top 10"] ? { w: sp52["vs Top 10"].w, n: sp52["vs Top 10"].m } : null,
        } : null;

        data = {
          matches: ms.length, lastDate: ms[0].date, lastSurface: ms[0].surface || null,
          spw, hold: holdFromPoint(spw), rpw: avg(nums(ms.map((m) => m.rpw))), spwAdj, rpwAdj, quality,
          acePct: ace, acesPerServiceGame: ace * 6.3, rank,
          wins: res.filter(Boolean).length, results: res.length,
          winRate: res.length >= 5 ? res.filter(Boolean).length / res.length : null,
          form: ms.slice(0, 5).map((m) => (m.win === true ? "V" : m.win === false ? "D" : "?")).join(""),
          surf, fatigue, clutch, serve, levels, hands, speed, career: car,
          elo, bio: b,
          set1Over95: s1.length ? s1.filter((m) => (m.set1 as number) >= 10).length / s1.length : null,
          set1Sample: s1.length,
          set1Recent: all.filter((m) => m.set1 !== null).slice(0, 40).map((m) => ({ g: m.set1, s: m.surface, w: m.win, o: m.opp, d: m.date })),
        };
      }
    }
  } catch (_) { data = null; }
  const entry = { at: Date.now(), data, rows: all, h2h: h2hMap };
  cache.set(key, entry);
  return entry;
}

// ---------- Face-à-face, d'après l'historique d'un des deux joueurs
function sameName(opp: string, target: string) {
  const o = norm(opp), t = norm(target), last = norm(target.trim().split(/\s+/).pop() || "");
  return o === t || (!!last && o.endsWith(last) && o[0] === t[0]);
}
function h2hFrom(rows: M[], other: string) {
  const ms = rows.filter((m) => m.opp && m.win !== null && sameName(m.opp, other));
  if (!ms.length) return { a: 0, b: 0, n: 0, surf: {}, last: null };
  const surf: Record<string, { a: number; b: number }> = {};
  for (const m of ms) { const s = (surf[m.surface] = surf[m.surface] || { a: 0, b: 0 }); m.win ? s.a++ : s.b++; }
  const l = ms[0];
  return { a: ms.filter((m) => m.win).length, b: ms.filter((m) => !m.win).length, n: ms.length, surf, last: { date: l.date, aWon: l.win, surface: l.surface, score: l.score, tourney: l.tourney } };
}
const flip = (h: ReturnType<typeof h2hFrom>) => ({
  a: h.b, b: h.a, n: h.n,
  surf: Object.fromEntries(Object.entries(h.surf).map(([k, v]) => [k, { a: v.b, b: v.a }])),
  last: h.last ? { ...h.last, aWon: !h.last.aWon } : null,
});

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  const url = new URL(req.url);
  const names = (url.searchParams.get("players") || "").split(",").map((s) => s.trim()).filter(Boolean).slice(0, 40);
  if (!names.length) {
    return new Response(JSON.stringify({ error: "Paramètre players manquant" }), { status: 400, headers: { ...CORS, "Content-Type": "application/json" } });
  }
  const res: Record<string, unknown> = {};
  const rows: Record<string, M[]> = {};
  const careers: Record<string, Record<string, { w: number; l: number; tbW: number | null; tbN: number | null; first: string; last: string }>> = {};
  await elos();
  for (let i = 0; i < names.length; i += 8) {
    const part = names.slice(i, i + 8);
    const got = await Promise.all(part.map(player));
    part.forEach((n, j) => { res[n] = got[j] ? got[j]!.data : null; rows[n] = got[j] ? got[j]!.rows : []; careers[n] = got[j] ? got[j]!.h2h : {}; });
  }
  const h2h: Record<string, unknown> = {};
  for (const pair of (url.searchParams.get("h2h") || "").split(";").slice(0, 60)) {
    const [a, b] = pair.split("|").map((s) => s && s.trim());
    if (!a || !b) continue;
    const recent = rows[a] && rows[a].length ? h2hFrom(rows[a], b) : rows[b] && rows[b].length ? flip(h2hFrom(rows[b], a)) : null;
    const ca = careers[a] && careers[a][norm(b)], cb = careers[b] && careers[b][norm(a)];
    if (ca || cb) {
      // carrière complète ; détail par surface et dernier match d'après les résultats récents
      const c = ca ? { a: ca.w, b: ca.l, tbA: ca.tbW, tbN: ca.tbN, first: ca.first, last: ca.last } : { a: cb!.l, b: cb!.w, tbA: cb!.tbN !== null && cb!.tbW !== null ? cb!.tbN - cb!.tbW : null, tbN: cb!.tbN, first: cb!.first, last: cb!.last };
      h2h[a + "|" + b] = { a: c.a, b: c.b, n: c.a + c.b, career: true, tbA: c.tbA, tbN: c.tbN, first: c.first, lastDate: c.last, surf: recent ? recent.surf : {}, last: recent ? recent.last : null };
    } else if (recent) h2h[a + "|" + b] = recent;
  }
  return new Response(JSON.stringify({ source: "tennisabstract.com", version: 8, players: res, h2h }), {
    headers: { ...CORS, "Content-Type": "application/json", "Cache-Control": "public, max-age=1800" },
  });
});
