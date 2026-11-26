import { css } from "../color.js";
import { esc } from "../format.js";
import { isCapital } from "../world.js";
import { yieldGrid, amenities, industries, gdpRow, popLine, growthSpan, showPanel, hidePanel } from "./infoPanel.js";

// City landmarks (data/landmarks.json, optional): loaded once, on the first city panel.
let landmarksP = null;
const loadLandmarks = () => (landmarksP ??= fetch("data/landmarks.json").then((r) => (r.ok ? r.json() : null)).catch(() => null));

function landmarkList(doc, city) {
  const list = doc?.cities?.[city.id];
  if (!list?.length) return `<p class="muted">No building of the federal cultural property inventory (A objects) in this city's communes.</p>`;
  const rows = list.map((l, k) => {
    const link = l.wikidata ? ` <a href="https://www.wikidata.org/wiki/${esc(l.wikidata)}" target="_blank" rel="noopener" class="muted">↗</a>` : "";
    const local = l.name_local && l.name_local !== l.name ? ` <span class="muted">(${esc(l.name_local)})</span>` : "";
    return `<li><b>${k + 1}. ${esc(l.name)}</b>${local}${link}<br><span class="muted">${esc(l.type)}${l.area ? " · area" : ""} · ${l.sitelinks} Wikipedia editions</span></li>`;
  }).join("");
  return `<ol class="landmarks" style="list-style:none;padding:0;margin:0;display:grid;gap:6px">${rows}</ol><p class="muted" style="margin-top:6px">${esc(doc.rule || "")}</p>`;
}

/**
 * ctx: {w, nation, onClose, onPedia, onState(stateIndex)}
 */
export function openCityPanel(city, ctx) {
  const { w, nation } = ctx;
  const n = nation.nation;
  const owner = city.cell != null ? w.raw.owner[city.cell] : -1;
  const col = css(w.stateColor[owner] || [190, 190, 190]);

  // The city's states as links to their state panels.
  const states = (city.states || [])
    .map((abbr) => ({ abbr, i: w.raw.states.findIndex((s) => s.abbr === abbr) }))
    .map(({ abbr, i }) => (i >= 0 && ctx.onState
      ? `<button class="chip" data-state="${i}" title="Open ${esc(w.raw.states[i].name)}">${esc(abbr)}</button>`
      : `<span class="chip">${esc(abbr)}</span>`))
    .join("");

  const growth = growthSpan(city, n);

  showPanel({
    kind: "city",
    stripe: col,
    title: city.name,
    titleHtml: `${isCapital(city) ? `<span class="cap" title="National capital">★</span> ` : ""}${esc(city.name)}`,
    sub: `${esc(city.full || "")}${states ? `<div class="chips">${states}</div>` : ""}`,
    headExtra: popLine(city, growth),
    sections: [
      { title: "Yields", html: `<div class="yield-grid">${yieldGrid(nation, city.yields)}</div>` },
      { title: "Landmarks", html: `<div data-landmarks>Loading…</div>` },
      { title: "Economy", html: gdpRow(city) },
      { title: "Districts · where people work", html: industries(city, nation) },
    ],
    foot: `Source: FSO, ${esc(nation.vintage)}${nation.gdp_vintage ? `; GDP: ${esc(nation.gdp_vintage)}, split by jobs` : ""}; landmarks: BABS KGS inventory, Wikidata.
      Green ×N = this industry's share of jobs is N× the Swiss share.`,
    onClose: ctx.onClose,
    onPedia: ctx.onPedia,
    wire(panel) {
      panel.querySelectorAll("[data-state]").forEach((b) => (b.onclick = () => ctx.onState(+b.dataset.state)));
      loadLandmarks().then((doc) => {
        const el = panel.querySelector("[data-landmarks]");
        if (el) el.innerHTML = landmarkList(doc, city);
      });
    },
  });
}

export const closeCityPanel = hidePanel;
