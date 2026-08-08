/* ======================================================================
   DATA
   ====================================================================== */
const CONCERTS = JSON.parse(document.getElementById('data-concerts').textContent);

/*
 * V4.6 — distinguish real Cure-family concerts from guest appearances.
 *
 * Cure Concerts Guide sometimes includes an entire set by another artist when
 * a Cure member guests with them (e.g. Olivia Rodrigo / Robert Smith).
 * Those events stay searchable in the archive, but MUST NOT contaminate
 * The Cure concert/song/ranking/map statistics.
 */
const CORE_ARTISTS = new Set(['the cure', 'easy cure', 'malice']);

function normArtist(value){
  return String(value || 'The Cure')
    .trim()
    .replace(/:\s*$/, '')
    .toLowerCase();
}

function isCoreConcert(c){
  if(c && c.isTheCureConcert === false) return false;
  if(c && c.eventType === 'Guest appearance') return false;
  return CORE_ARTISTS.has(normArtist(c?.artist));
}

function isGuestAppearance(c){
  return !isCoreConcert(c);
}

function appearanceLabel(c){
  if(!isGuestAppearance(c)) return '';
  const artist = String(c.artist || '').replace(/:\s*$/, '').trim();
  return artist || 'Artiste invité';
}

const CORE_CONCERTS = CONCERTS.filter(isCoreConcert);
const GUEST_APPEARANCES = CONCERTS.filter(isGuestAppearance);

/* ======================================================================
   HELPERS
   ====================================================================== */
const fmtInt = n => n==null ? '—' : n.toLocaleString('fr-FR');
const esc = s => (s==null?'':String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function fmtDate(d){
  if(!d) return '—';
  const parts = d.split('-');
  if(parts.length!==3) return d;
  const months = ['jan.','fév.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.'];
  const y=parts[0], m=parseInt(parts[1],10)-1, day=parseInt(parts[2],10);
  return `${day} ${months[m]} ${y}`;
}

/* ======================================================================
   AGGREGATES (computed once)
   Main statistics intentionally use CORE_CONCERTS only.
   ====================================================================== */
const songMap = new Map();   // song -> {count, years:Map, tours:Set, concerts:[]}
const venueMap = new Map();
const cityMap = new Map();
const countryMap = new Map();
const tourMap = new Map();
const yearMap = new Map();
const decadeMap = new Map();

const allCountryMap = new Map();
const allTourMap = new Map();

function bump(map, key, inc=1){
  if(key==null || key==='') return;
  map.set(key, (map.get(key)||0)+inc);
}

CONCERTS.forEach(c=>{
  bump(allCountryMap, c.country);
  bump(allTourMap, c.tour);
});

CORE_CONCERTS.forEach(c=>{
  bump(venueMap, c.venue);
  bump(cityMap, c.city);
  bump(countryMap, c.country);
  bump(tourMap, c.tour);
  bump(yearMap, c.year);
  if(c.year){
    const dec = Math.floor(c.year/10)*10;
    bump(decadeMap, dec);
  }
  (c.setlist || []).forEach(entry=>{
    const s = entry.song;
    if(!s) return;
    if(!songMap.has(s)) songMap.set(s, {count:0, years:new Map(), tours:new Set(), concerts:[]});
    const rec = songMap.get(s);
    rec.count++;
    if(c.year) rec.years.set(c.year, (rec.years.get(c.year)||0)+1);
    if(c.tour) rec.tours.add(c.tour);
    rec.concerts.push(c);
  });
});

const TOTAL_CONCERTS = CORE_CONCERTS.length;
const TOTAL_GUEST_APPEARANCES = GUEST_APPEARANCES.length;
const TOTAL_SETLIST_ENTRIES = CORE_CONCERTS.reduce((a,c)=>a+(c.setlist || []).length,0);
const TOTAL_UNIQUE_SONGS = songMap.size;
const TOTAL_COUNTRIES = countryMap.size;
const YEARS = CORE_CONCERTS.map(c=>c.year).filter(Boolean);
const YEAR_MIN = Math.min(...YEARS), YEAR_MAX = Math.max(...YEARS);

/* ======================================================================
   KPI ROW
   ====================================================================== */
document.getElementById('kpi-row').innerHTML = `
  <div class="kpi"><div class="num">${fmtInt(TOTAL_CONCERTS)}</div><div class="lbl">Concerts Cure</div></div>
  ${TOTAL_GUEST_APPEARANCES ? `<div class="kpi"><div class="num">${fmtInt(TOTAL_GUEST_APPEARANCES)}</div><div class="lbl">Apparitions invitées</div></div>` : ``}
  <div class="kpi"><div class="num">${fmtInt(TOTAL_UNIQUE_SONGS)}</div><div class="lbl">Titres distincts</div></div>
  <div class="kpi"><div class="num">${fmtInt(TOTAL_SETLIST_ENTRIES)}</div><div class="lbl">Interprétations</div></div>
  <div class="kpi"><div class="num">${fmtInt(TOTAL_COUNTRIES)}</div><div class="lbl">Pays</div></div>
  <div class="kpi"><div class="num">${YEAR_MIN}–${YEAR_MAX}</div><div class="lbl">Période</div></div>
`;

document.getElementById('theme-toggle').addEventListener('click', ()=>{
  const html = document.documentElement;
  html.dataset.theme = html.dataset.theme==='light' ? 'dark' : 'light';
});

/* ======================================================================
   NAV / TABS
   ====================================================================== */
document.getElementById('nav').addEventListener('click', e=>{
  const btn = e.target.closest('button[data-tab]');
  if(!btn) return;
  document.querySelectorAll('#nav button').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+btn.dataset.tab).classList.add('active');
});

/* ======================================================================
   OVERVIEW TAB
   ====================================================================== */
function renderDecadesChart(){
  const decades = [...decadeMap.entries()].sort((a,b)=>a[0]-b[0]);
  const max = Math.max(...decades.map(d=>d[1]));
  const w=520, h=180, padL=44, padB=24, barGap=10;
  const barW = (w-padL-10)/decades.length - barGap;
  let bars='', labels='';
  decades.forEach((d,i)=>{
    const [dec,count]=d;
    const bh = (count/max)*(h-padB-20);
    const x = padL + i*((w-padL-10)/decades.length);
    const y = h-padB-bh;
    bars += `<rect class="chart-bar" x="${x}" y="${y}" width="${barW}" height="${bh}" rx="1"><title>${dec}s: ${count}</title></rect>`;
    bars += `<text x="${x+barW/2}" y="${y-6}" font-size="11" text-anchor="middle">${count}</text>`;
    labels += `<text x="${x+barW/2}" y="${h-6}" font-size="11" text-anchor="middle">${dec}s</text>`;
  });
  document.getElementById('chart-decades').innerHTML =
    `<svg class="chart-svg" viewBox="0 0 ${w} ${h}" width="100%" height="${h}">${bars}${labels}</svg>`;
}
renderDecadesChart();

function renderRankListInto(elId, entriesSorted, total, opts={}){
  const el = document.getElementById(elId);
  const max = entriesSorted.length ? entriesSorted[0][1] : 1;
  el.innerHTML = entriesSorted.map((e,i)=>`
    <li class="rank-row ${opts.clickable?'clickable':''}" ${opts.clickable?`data-val="${esc(e[0])}"`:''}>
      <span class="rank-idx">${String(i+1).padStart(2,'0')}</span>
      <span class="rank-main">
        <span class="rank-name">${esc(e[0])}</span>
        <span class="rank-bar-track"><span class="rank-bar-fill" style="width:${(e[1]/max*100).toFixed(0)}%"></span></span>
      </span>
      <span class="rank-count">${fmtInt(e[1])}</span>
    </li>
  `).join('');
}

function topN(map, n){
  return [...map.entries()].sort((a,b)=>b[1]-a[1]).slice(0,n);
}

renderRankListInto('top-countries', topN(countryMap,10), null, {clickable:true});
renderRankListInto('top-venues', topN(venueMap,10), null, {clickable:true});

function renderTracklistOverview(){
  const top = topN(songMap.entries ? songMap : songMap, 0);
}
(function(){
  const arr = [...songMap.entries()].map(([name,rec])=>[name,rec.count]).sort((a,b)=>b[1]-a[1]).slice(0,10);
  const el = document.getElementById('top-songs-overview');
  el.innerHTML = arr.map((e,i)=>`
    <li class="track-row" data-song="${esc(e[0])}">
      <span class="track-side">A${i+1}</span>
      <span class="track-name">${esc(e[0])}</span>
      <span class="track-count">${fmtInt(e[1])}×</span>
    </li>
  `).join('');
  el.addEventListener('click', e=>{
    const row = e.target.closest('.track-row');
    if(!row) return;
    goToSong(row.dataset.song);
  });
})();

document.getElementById('top-countries').addEventListener('click', e=>{
  const row = e.target.closest('.rank-row'); if(!row) return;
  document.querySelector('button[data-tab="concerts"]').click();
  document.getElementById('f-country').value = row.dataset.val;
  applyFilters();
});
document.getElementById('top-venues').addEventListener('click', e=>{
  const row = e.target.closest('.rank-row'); if(!row) return;
  document.querySelector('button[data-tab="concerts"]').click();
  document.getElementById('f-search').value = row.dataset.val;
  applyFilters();
});

/* ======================================================================
   CONCERTS TAB — filters, sort, paginate
   ====================================================================== */
const countrySel = document.getElementById('f-country');
[...allCountryMap.keys()].sort().forEach(c=>{
  const o=document.createElement('option'); o.value=c; o.textContent=`${c} (${allCountryMap.get(c)})`;
  countrySel.appendChild(o);
});
const tourSel = document.getElementById('f-tour');
[...allTourMap.keys()].sort((a,b)=>allTourMap.get(b)-allTourMap.get(a)).forEach(t=>{
  const o=document.createElement('option'); o.value=t; o.textContent=`${t} (${allTourMap.get(t)})`;
  tourSel.appendChild(o);
});
const songSel = document.getElementById('f-song');

const resetField = document.getElementById('f-reset')?.closest('.field');
const typeField = document.createElement('div');
typeField.className = 'field';
typeField.innerHTML = `
  <label>Type</label>
  <select id="f-event-type">
    <option value="">Tous</option>
    <option value="core">Concerts Cure</option>
    <option value="guest">Apparitions invitées</option>
  </select>`;
if(resetField) resetField.parentNode.insertBefore(typeField, resetField);
const eventTypeSel = document.getElementById('f-event-type');

[...songMap.keys()].sort().forEach(s=>{
  const o=document.createElement('option'); o.value=s; o.textContent=s;
     songSel.appendChild(o);
});

let sortKey='date', sortDir='asc', page=1;
const PAGE_SIZE=40;
let filtered = CONCERTS.slice();

function applyFilters(){
  const q = document.getElementById('f-search').value.trim().toLowerCase();
  const country = countrySel.value;
  const tour = tourSel.value;
  const yMin = parseInt(document.getElementById('f-year-min').value)||null;
  const yMax = parseInt(document.getElementById('f-year-max').value)||null;
  const song = songSel.value;
  const eventType = eventTypeSel?.value || '';

  filtered = CONCERTS.filter(c=>{
    if(eventType==='core' && !isCoreConcert(c)) return false;
    if(eventType==='guest' && !isGuestAppearance(c)) return false;
    if(country && c.country!==country) return false;
    if(tour && c.tour!==tour) return false;
    if(yMin && (!c.year || c.year<yMin)) return false;
    if(yMax && (!c.year || c.year>yMax)) return false;
    if(song && !c.setlist.some(s=>s.song===song)) return false;
    if(q){
      const hay = `${c.artist||''} ${c.city||''} ${c.venue||''} ${c.tour||''} ${c.country||''}`.toLowerCase();
      if(!hay.includes(q)) return false;
    }
    return true;
  });
  page=1;
  sortAndRender();
}

function sortAndRender(){
  filtered.sort((a,b)=>{
    let va=a[sortKey], vb=b[sortKey];
    if(va==null) va = (typeof vb==='number') ? -Infinity : '';
    if(vb==null) vb = (typeof va==='number') ? -Infinity : '';
    if(typeof va==='string') va=va.toLowerCase();
    if(typeof vb==='string') vb=vb.toLowerCase();
    if(va<vb) return sortDir==='asc'?-1:1;
    if(va>vb) return sortDir==='asc'?1:-1;
    return 0;
  });
  renderTable();
}

function renderTable(){
  document.getElementById('results-count').textContent = `${fmtInt(filtered.length)} concert${filtered.length>1?'s':''}`;
  const start=(page-1)*PAGE_SIZE, end=start+PAGE_SIZE;
  const rows = filtered.slice(start,end);
  document.getElementById('concerts-tbody').innerHTML = rows.map(c=>`
    <tr data-id="${c.id}">
      <td class="date-cell">${fmtDate(c.date)}</td>
      <td class="city-cell">${esc(c.city)||'—'} ${isGuestAppearance(c)?'<span class="badge" title="Cette ligne est une apparition d’un membre de The Cure chez un autre artiste et n’est pas comptée dans les statistiques principales.">APPARITION</span>':''}</td>
      <td>${isGuestAppearance(c)?`<strong>${esc(appearanceLabel(c))}</strong> · `:''}${esc(c.venue)||'—'}</td>
      <td>${esc(c.country)||'—'}</td>
      <td>${esc(c.tour)||'—'}</td>
      <td>${c.songsPlayed ?? '—'}</td>
      <td>${c.attendance ? fmtInt(c.attendance) + (c.soldOut?' <span class="badge">SOLD OUT</span>':'') : (c.soldOut?'<span class="badge">SOLD OUT</span>':'—')}</td>
    </tr>
  `).join('') || `<tr><td colspan="7"><div class="empty-state">Aucun concert ne correspond à ces critères.</div></td></tr>`;

  const totalPages = Math.max(1, Math.ceil(filtered.length/PAGE_SIZE));
  const pag = document.getElementById('pagination');
  pag.innerHTML = `
    <button id="pg-prev" ${page<=1?'disabled':''}>‹</button>
    <span>Page ${page} / ${totalPages}</span>
    <button id="pg-next" ${page>=totalPages?'disabled':''}>›</button>
  `;
  document.getElementById('pg-prev')?.addEventListener('click', ()=>{page--; renderTable();});
  document.getElementById('pg-next')?.addEventListener('click', ()=>{page++; renderTable();});
}

document.getElementById('concerts-tbody').addEventListener('click', e=>{
  const tr = e.target.closest('tr[data-id]'); if(!tr) return;
  openTicket(parseInt(tr.dataset.id,10));
});

document.querySelectorAll('#tab-concerts thead th[data-key]').forEach(th=>{
  th.addEventListener('click', ()=>{
    const key = th.dataset.key;
    if(sortKey===key){ sortDir = sortDir==='asc'?'desc':'asc'; }
    else { sortKey=key; sortDir='asc'; }
    document.querySelectorAll('#tab-concerts thead th').forEach(t=>t.classList.remove('sorted','sorted-asc'));
    th.classList.add(sortDir==='asc'?'sorted-asc':'sorted');
    sortAndRender();
  });
});

['f-search','f-country','f-tour','f-year-min','f-year-max','f-song','f-event-type'].forEach(id=>{
  document.getElementById(id).addEventListener('input', applyFilters);
  document.getElementById(id).addEventListener('change', applyFilters);
});
document.getElementById('f-reset').addEventListener('click', ()=>{
  document.getElementById('f-search').value='';
  countrySel.value=''; tourSel.value=''; songSel.value=''; if(eventTypeSel) eventTypeSel.value='';
  document.getElementById('f-year-min').value='';
  document.getElementById('f-year-max').value='';
  applyFilters();
});

sortAndRender();

/* ======================================================================
   TICKET MODAL
   ====================================================================== */
function openTicket(id){
  const c = CONCERTS.find(x=>x.id===id);
  if(!c) return;
  document.getElementById('ticket-city').textContent = `${c.city||'Lieu inconnu'} — ${fmtDate(c.date)}`;
  document.getElementById('ticket-venue').textContent = `${isGuestAppearance(c)?appearanceLabel(c)+' — ':''}${c.venue||'Salle inconnue'}${c.country?', '+c.country:''}`;
  document.getElementById('ticket-meta').innerHTML = `
    <div><div class="m-lbl">Artiste</div><div class="m-val">${esc(c.artist)||'The Cure'}</div></div>
    <div><div class="m-lbl">Type</div><div class="m-val">${isGuestAppearance(c)?'<span class="badge">APPARITION INVITÉE</span>':'Concert Cure'}</div></div>
    <div><div class="m-lbl">Tournée</div><div class="m-val">${esc(c.tour)||'—'}</div></div>
    <div><div class="m-lbl">Jour</div><div class="m-val">${esc(c.dow)||'—'}</div></div>
    <div><div class="m-lbl">Chansons</div><div class="m-val">${c.songsPlayed ?? c.setlist.length ?? '—'}</div></div>
    <div><div class="m-lbl">Affluence</div><div class="m-val">${c.attendance ? fmtInt(c.attendance) : '—'}</div></div>
    <div><div class="m-lbl">Capacité</div><div class="m-val">${c.capacity ? fmtInt(c.capacity) : '—'}</div></div>
    <div><div class="m-lbl">Sold out</div><div class="m-val">${c.soldOut ? 'Oui' : 'Non'}</div></div>
  `;
  const guestNotice = isGuestAppearance(c)
    ? `<div class="panel" style="margin-bottom:16px;padding:14px"><strong>Apparition invitée</strong><br><span style="color:var(--text-dim)">Cette setlist appartient à ${esc(appearanceLabel(c))}. Elle est conservée à titre documentaire mais ses titres ne sont pas comptés dans les statistiques musicales de The Cure.</span></div>`
    : '';
  if(c.setlist.length===0){
    document.getElementById('ticket-body').innerHTML = guestNotice + `<div class="empty-state">Setlist inconnue pour cette date.</div>`;
  } else {
    const sections = {};
    c.setlist.forEach(s=>{ (sections[s.section] = sections[s.section]||[]).push(s); });
    const sectionOrder = ['Mainset','Encore 1','Encore 2','Encore 3','Encore 4'];
    const orderedSections = Object.entries(sections).sort(([a],[b])=>{
      const ia = sectionOrder.indexOf(a), ib = sectionOrder.indexOf(b);
      if(ia === -1 && ib === -1) return a.localeCompare(b, 'fr');
      if(ia === -1) return 1;
      if(ib === -1) return -1;
      return ia - ib;
    });
    document.getElementById('ticket-body').innerHTML = guestNotice + orderedSections.map(([sec,items])=>{
      const songs = items.slice().sort((a,b)=>(a.pos ?? 999) - (b.pos ?? 999));
      return `
      <div class="setlist-section">
        <div class="sec-title">${esc(sec)}</div>
        <ol>${songs.map(s=>`<li>${esc(s.song)}</li>`).join('')}</ol>
      </div>
    `;
    }).join('');
  }
  document.getElementById('ticket-foot').innerHTML = `${esc(c.address)||''}`;
  document.getElementById('overlay').classList.add('open');
}
document.getElementById('ticket-close').addEventListener('click', ()=>document.getElementById('overlay').classList.remove('open'));
document.getElementById('overlay').addEventListener('click', e=>{ if(e.target.id==='overlay') e.currentTarget.classList.remove('open'); });
document.addEventListener('keydown', e=>{ if(e.key==='Escape') document.getElementById('overlay').classList.remove('open'); });

/* ======================================================================
   ALL TITLES TAB
   ====================================================================== */
const countryCities = new Map();
CORE_CONCERTS.forEach(c=>{
  if(!c.country || !c.city) return;
  if(!countryCities.has(c.country)) countryCities.set(c.country, new Set());
  countryCities.get(c.country).add(c.city);
});

const atScopeSel = document.getElementById('at-scope');
const atCountrySel = document.getElementById('at-country');
const atCitySel = document.getElementById('at-city');
const atCountryField = document.getElementById('at-country-field');
const atCityField = document.getElementById('at-city-field');
const atSearchInput = document.getElementById('at-search');

[...countryMap.keys()].sort().forEach(c=>{
  const o=document.createElement('option'); o.value=c; o.textContent=`${c} (${countryMap.get(c)} concerts)`;
  atCountrySel.appendChild(o);
});

function populateAtCities(countryFilter){
  atCitySel.innerHTML = '<option value="">— choisir —</option>';
  let cities;
  if(countryFilter && countryCities.has(countryFilter)){
    cities = [...countryCities.get(countryFilter)];
  } else {
    cities = [...cityMap.keys()];
  }
  cities.sort((a,b)=>(cityMap.get(b)||0)-(cityMap.get(a)||0));
  cities.forEach(city=>{
    const o=document.createElement('option'); o.value=city; o.textContent=`${city} (${cityMap.get(city)||0} concerts)`;
    atCitySel.appendChild(o);
  });
}
populateAtCities(null);

atScopeSel.addEventListener('change', ()=>{
  const v = atScopeSel.value;
  atCountryField.style.display = (v==='country' || v==='city') ? '' : 'none';
  atCityField.style.display = (v==='city') ? '' : 'none';
  if(v==='world'){ atCountrySel.value=''; atCitySel.value=''; }
  renderAllTitles();
});
atCountrySel.addEventListener('change', ()=>{
  populateAtCities(atCountrySel.value || null);
  atCitySel.value='';
  renderAllTitles();
});
atCitySel.addEventListener('change', renderAllTitles);
atSearchInput.addEventListener('input', renderAllTitles);
document.getElementById('at-reset').addEventListener('click', ()=>{
  atScopeSel.value='world';
  atCountryField.style.display='none';
  atCityField.style.display='none';
  atCountrySel.value=''; atCitySel.value=''; atSearchInput.value='';
  populateAtCities(null);
  renderAllTitles();
});

let atSortKey='count', atSortDir='desc';

document.querySelectorAll('#tab-alltitles thead th[data-atkey]').forEach(th=>{
  th.addEventListener('click', ()=>{
    const key = th.dataset.atkey;
    if(atSortKey===key){ atSortDir = atSortDir==='asc'?'desc':'asc'; }
    else { atSortKey=key; atSortDir = (key==='song') ? 'asc' : 'desc'; }
    document.querySelectorAll('#tab-alltitles thead th').forEach(t=>t.classList.remove('sorted','sorted-asc'));
    th.classList.add(atSortDir==='asc'?'sorted-asc':'sorted');
    renderAllTitles();
  });
});

function renderAllTitles(){
  const scope = atScopeSel.value;
  const country = atCountrySel.value;
  const city = atCitySel.value;
  const q = atSearchInput.value.trim().toLowerCase();

  let scopeConcerts = CORE_CONCERTS;
  let scopeLabel = 'dans le monde';
if(scope==='country' && country){
  scopeConcerts = CORE_CONCERTS.filter(c=>c.country===country);
  scopeLabel = `en ${country}`;
} else if(scope==='city' && city){
  scopeConcerts = CORE_CONCERTS.filter(c=>c.city===city);
  scopeLabel = `à ${city}`;
}
       const localMap = new Map();
  scopeConcerts.forEach(c=>{
    c.setlist.forEach(entry=>{
      const s = entry.song;
      if(!localMap.has(s)) localMap.set(s, {count:0, first:null, last:null});
      const rec = localMap.get(s);
      rec.count++;
      if(!rec.first || c.date < rec.first.date) rec.first = c;
      if(!rec.last || c.date > rec.last.date) rec.last = c;
    });
  });

  const concertsWithSetlist = scopeConcerts.filter(c=>c.setlist.length>0).length;

  let rows = [...localMap.entries()].map(([song, rec])=>({
    song, count: rec.count, first: rec.first, last: rec.last,
    pct: concertsWithSetlist ? (rec.count/concertsWithSetlist*100) : 0
  }));

  if(q){
    rows = rows.filter(r=>r.song.toLowerCase().includes(q));
  }

  rows.sort((a,b)=>{
    let va, vb;
    if(atSortKey==='song'){ va=a.song.toLowerCase(); vb=b.song.toLowerCase(); }
    else if(atSortKey==='count'){ va=a.count; vb=b.count; }
    else if(atSortKey==='pct'){ va=a.pct; vb=b.pct; }
    else if(atSortKey==='first'){ va=a.first?a.first.date:''; vb=b.first?b.first.date:''; }
    else if(atSortKey==='last'){ va=a.last?a.last.date:''; vb=b.last?b.last.date:''; }
    if(va<vb) return atSortDir==='asc'?-1:1;
    if(va>vb) return atSortDir==='asc'?1:-1;
    return 0;
  });

  document.getElementById('at-results-count').textContent =
    `${fmtInt(rows.length)} titre${rows.length>1?'s':''} distinct${rows.length>1?'s':''} · ${fmtInt(concertsWithSetlist)} concert${concertsWithSetlist>1?'s':''} avec setlist connue ${scopeLabel} (sur ${fmtInt(scopeConcerts.length)} au total)`;

  document.getElementById('alltitles-tbody').innerHTML = rows.length ? rows.map((r,i)=>`
    <tr data-song="${esc(r.song)}">
      <td class="date-cell">${i+1}</td>
      <td class="city-cell">${esc(r.song)}</td>
      <td>${fmtInt(r.count)}</td>
      <td>${r.pct.toFixed(1)}%</td>
      <td>${r.first ? fmtDate(r.first.date) + ' · ' + (esc(r.first.city)||'—') : '—'}</td>
      <td>${r.last ? fmtDate(r.last.date) + ' · ' + (esc(r.last.city)||'—') : '—'}</td>
    </tr>
  `).join('') : `<tr><td colspan="6"><div class="empty-state">Aucun titre ne correspond à ces critères pour cette échelle.</div></td></tr>`;

  document.querySelectorAll('#alltitles-tbody tr[data-song]').forEach(tr=>{
    tr.addEventListener('click', ()=>{
      document.querySelector('button[data-tab="songs"]').click();
      goToSong(tr.dataset.song);
    });
  });
}
renderAllTitles();

/* ======================================================================
   RANKINGS TAB
   ====================================================================== */
function renderRankingsTab(){
  const cat = document.getElementById('rank-category').value;
  const limitRaw = document.getElementById('rank-limit').value;
  const limit = limitRaw==='all' ? Infinity : parseInt(limitRaw,10);
  let map, clickable=false;
  if(cat==='songs'){ map = new Map([...songMap.entries()].map(([k,v])=>[k,v.count])); clickable='song'; }
  else if(cat==='venues'){ map = venueMap; clickable='search'; }
  else if(cat==='cities'){ map = cityMap; clickable='search'; }
  else if(cat==='countries'){ map = countryMap; clickable='country'; }
  else if(cat==='tours'){ map = tourMap; clickable='tour'; }
  else if(cat==='years'){ map = yearMap; clickable='year'; }

  const entries = topN(map, limit);
  const el = document.getElementById('rank-full-list');
  const max = entries.length ? entries[0][1] : 1;
  el.innerHTML = entries.map((e,i)=>`
    <li class="rank-row clickable" data-val="${esc(e[0])}">
      <span class="rank-idx">${String(i+1).padStart(2,'0')}</span>
      <span class="rank-main">
        <span class="rank-name">${esc(e[0])}</span>
        <span class="rank-bar-track"><span class="rank-bar-fill" style="width:${(e[1]/max*100).toFixed(0)}%"></span></span>
      </span>
      <span class="rank-count">${fmtInt(e[1])}</span>
    </li>
  `).join('');

  [...el.querySelectorAll('.rank-row')].forEach(row=>{
    row.addEventListener('click', ()=>{
      const val = row.dataset.val;
      if(clickable==='song'){
        document.querySelector('button[data-tab="songs"]').click();
        goToSong(val);
      } else {
        document.querySelector('button[data-tab="concerts"]').click();
        if(clickable==='country') countrySel.value=val;
        else if(clickable==='tour') tourSel.value=val;
        else if(clickable==='year'){
          document.getElementById('f-year-min').value=val;
          document.getElementById('f-year-max').value=val;
        }
        else document.getElementById('f-search').value=val;
        applyFilters();
      }
    });
  });
}
document.getElementById('rank-category').addEventListener('change', renderRankingsTab);
document.getElementById('rank-limit').addEventListener('change', renderRankingsTab);
renderRankingsTab();

/* ======================================================================
   SONGS TAB
   ====================================================================== */
const songSearchInput = document.getElementById('song-search-input');
const songDropdown = document.getElementById('song-dropdown');
const allSongNames = [...songMap.keys()].sort();

function bindSongSearch(input, dropdown, onPick){
  input.addEventListener('input', ()=>{
    const q = input.value.trim().toLowerCase();
    if(!q){ dropdown.classList.remove('open'); return; }
    const matches = allSongNames.filter(s=>s.toLowerCase().includes(q)).slice(0,30);
    dropdown.innerHTML = matches.map(s=>`<div data-song="${esc(s)}"><span>${esc(s)}</span><span style="color:var(--text-faint)">${songMap.get(s).count}×</span></div>`).join('') || `<div style="color:var(--text-faint)">Aucun résultat</div>`;
    dropdown.classList.add('open');
  });
  dropdown.addEventListener('click', e=>{
    const row = e.target.closest('div[data-song]'); if(!row) return;
    onPick(row.dataset.song);
    dropdown.classList.remove('open');
  });
  document.addEventListener('click', e=>{
    if(!input.contains(e.target) && !dropdown.contains(e.target)) dropdown.classList.remove('open');
  });
}

function goToSong(name){
  document.querySelector('button[data-tab="songs"]').click();
  songSearchInput.value = name;
  renderSongDetail(name);
}

function renderSongDetail(name){
  const rec = songMap.get(name);
  if(!rec){
    document.getElementById('song-detail').innerHTML = `<div class="empty-state">Titre introuvable.</div>`;
    return;
  }
  const sortedConcerts = rec.concerts.slice().sort((a,b)=>a.date.localeCompare(b.date));
  const first = sortedConcerts[0], last = sortedConcerts[sortedConcerts.length-1];
  const years = [...rec.years.entries()].sort((a,b)=>a[0]-b[0]);
  const maxY = Math.max(...years.map(y=>y[1]));

  const w=Math.max(560, years.length*26), h=160, padB=22;
  let bars='';
  years.forEach((y,i)=>{
    const bw = Math.max(6, (w/years.length)-4);
    const x = i*(w/years.length);
    const bh = (y[1]/maxY)*(h-padB-16);
    bars += `<rect class="chart-bar" x="${x}" y="${h-padB-bh}" width="${bw}" height="${bh}" rx="1"><title>${y[0]}: ${y[1]}</title></rect>`;
    if(years.length<45) bars += `<text x="${x+bw/2}" y="${h-6}" font-size="9" text-anchor="middle">${String(y[0]).slice(2)}</text>`;
  });

  document.getElementById('song-detail').innerHTML = `
    <div class="song-detail-head">
      <h3>${esc(name)}</h3>
      <span class="badge">${rec.count} interprétations</span>
    </div>
    <div class="grid-3" style="margin-bottom:24px;">
      <div class="panel"><h3>Première fois</h3><div style="color:var(--text)">${fmtDate(first.date)}</div><div style="color:var(--text-dim); font-size:13px; margin-top:4px;">${esc(first.city)||'—'} · ${esc(first.venue)||'—'}</div></div>
      <div class="panel"><h3>Dernière fois</h3><div style="color:var(--text)">${fmtDate(last.date)}</div><div style="color:var(--text-dim); font-size:13px; margin-top:4px;">${esc(last.city)||'—'} · ${esc(last.venue)||'—'}</div></div>
      <div class="panel"><h3>Tournées</h3><div style="color:var(--text)">${rec.tours.size} tournée${rec.tours.size>1?'s':''}</div><div style="color:var(--text-dim); font-size:13px; margin-top:4px;">${[...rec.tours].slice(0,3).map(esc).join(', ')}${rec.tours.size>3?'…':''}</div></div>
    </div>
    <div class="panel" style="margin-bottom:24px;">
      <h3>Occurrences par année</h3>
      <div style="overflow-x:auto;"><svg class="chart-svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">${bars}</svg></div>
    </div>
    <div class="panel">
      <h3>Toutes les dates (${sortedConcerts.length})</h3>
      <div class="table-scroll" style="border:none; max-height:360px; overflow-y:auto;">
        <table>
          <thead><tr><th>Date</th><th>Ville</th><th>Salle</th><th>Tournée</th></tr></thead>
          <tbody>
            ${sortedConcerts.slice().reverse().map(c=>`<tr data-id="${c.id}"><td class="date-cell">${fmtDate(c.date)}</td><td class="city-cell">${esc(c.city)||'—'}</td><td>${esc(c.venue)||'—'}</td><td>${esc(c.tour)||'—'}</td></tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
  document.querySelectorAll('#song-detail tbody tr[data-id]').forEach(tr=>{
    tr.addEventListener('click', ()=>openTicket(parseInt(tr.dataset.id,10)));
  });
}

bindSongSearch(songSearchInput, songDropdown, name=>{
  songSearchInput.value = name;
  renderSongDetail(name);
});

/* ======================================================================
   COMPARE TAB
   ====================================================================== */
const compareInput = document.getElementById('compare-search-input');
const compareDropdown = document.getElementById('compare-dropdown');
const compareColors = ['#e63a56','#a897c9','#c9a15f','#6fb3a8'];
let compareList = [];

bindSongSearch(compareInput, compareDropdown, name=>{
  if(compareList.includes(name) || compareList.length>=4){
    compareInput.value='';
    return;
  }
  compareList.push(name);
  compareInput.value='';
  renderCompare();
});

function renderCompare(){
  document.getElementById('compare-pills').innerHTML = compareList.map((s,i)=>`
    <span class="pill"><span class="swatch" style="background:${compareColors[i]}"></span>${esc(s)}<button data-song="${esc(s)}">✕</button></span>
  `).join('') || `<span style="color:var(--text-faint); font-size:13px;">Aucune chanson sélectionnée — ajoutez-en jusqu'à 4.</span>`;

  document.querySelectorAll('#compare-pills button').forEach(b=>{
    b.addEventListener('click', ()=>{
      compareList = compareList.filter(s=>s!==b.dataset.song);
      renderCompare();
    });
  });

  const tbody = document.querySelector('#compare-table tbody');
  tbody.innerHTML = compareList.map(s=>{
    const rec = songMap.get(s);
    const sc = rec.concerts.slice().sort((a,b)=>a.date.localeCompare(b.date));
    return `<tr><td>${esc(s)}</td><td>${rec.count}</td><td>${fmtDate(sc[0].date)}</td><td>${fmtDate(sc[sc.length-1].date)}</td><td>${rec.tours.size}</td></tr>`;
  }).join('') || `<tr><td colspan="5" style="color:var(--text-faint)">—</td></tr>`;

  if(compareList.length===0){
    document.getElementById('compare-chart').innerHTML = `<div class="empty-state">Ajoutez des chansons pour comparer leur fréquence de jeu au fil des années.</div>`;
    return;
  }

  const yMinAll = YEAR_MIN, yMaxAll = YEAR_MAX;
  const allYears = [];
  for(let y=yMinAll; y<=yMaxAll; y++) allYears.push(y);

  const series = compareList.map(s=>{
    const rec = songMap.get(s);
    return allYears.map(y=>rec.years.get(y)||0);
  });

  const maxVal = Math.max(1, ...series.flat());
  const w = Math.max(700, allYears.length*16), h=240, padB=28, padL=6;
  const stepX = (w-padL)/allYears.length;

  let paths='';
  series.forEach((s,si)=>{
    let d='';
    s.forEach((v,i)=>{
      const x = padL + i*stepX + stepX/2;
      const y = h-padB - (v/maxVal)*(h-padB-16);
      d += (i===0?'M':'L')+x+','+y+' ';
    });
    paths += `<path d="${d}" fill="none" stroke="${compareColors[si]}" stroke-width="2"/>`;
         s.forEach((v,i)=>{
      if(v===0) return;
      const x = padL + i*stepX + stepX/2;
      const y = h-padB - (v/maxVal)*(h-padB-16);
      paths += `<circle cx="${x}" cy="${y}" r="2.5" fill="${compareColors[si]}"><title>${allYears[i]}: ${v}</title></circle>`;
    });
  });

  let labels='';
  allYears.forEach((y,i)=>{
    if(i%5===0){
      const x = padL + i*stepX + stepX/2;
      labels += `<text x="${x}" y="${h-8}" font-size="10" text-anchor="middle">${y}</text>`;
    }
  });

  document.getElementById('compare-chart').innerHTML =
    `<div style="overflow-x:auto;"><svg class="chart-svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">${paths}${labels}</svg></div>`;
}
renderCompare();

/* ======================================================================
   MAP TAB
   ====================================================================== */
function normalizeCountryName(raw){
  if(!raw) return null;
  if(raw.startsWith('USA/') || raw==='USA') return 'United States of America';
  if(raw.startsWith('Australia/')) return 'Australia';
  if(raw.startsWith('Canada/')) return 'Canada';
  const alias = {
    'England':'United Kingdom',
    'Scotland':'United Kingdom',
    'Wales':'United Kingdom',
    'Northern Ireland':'United Kingdom',
    'Brasil':'Brazil',
    'Czech Republic':'Czechia',
    'Czechoslovakia':'Czechia',
    'East-Germany':'Germany',
    'Yugoslavia':'Serbia'
  };
  return alias[raw] || raw;
}

const mapCountryCounts = new Map();
const mapCountryCityCounts = new Map();

CORE_CONCERTS.forEach(c=>{
  const topoName = normalizeCountryName(c.country);
  if(!topoName) return;
  bump(mapCountryCounts, topoName);
  if(!mapCountryCityCounts.has(topoName)){
    mapCountryCityCounts.set(topoName, new Map());
  }
  if(c.city) bump(mapCountryCityCounts.get(topoName), c.city);
});

let mapInitialized = false;
let mapGeojson = null;
let mapProjection = null;
let mapPathGen = null;
let mapSelectedFeature = null;
const MAP_VB_W = 960, MAP_VB_H = 500;

function initMapOnce(){
  if(mapInitialized) return;

  if(typeof d3==='undefined' || typeof topojson==='undefined'){
    document.getElementById('map-loading').textContent =
      "La carte nécessite une connexion internet pour charger d3.js (bibliothèque de rendu géographique).";
    return;
  }

  const topoData = JSON.parse(document.getElementById('data-topo').textContent);
  mapGeojson = topojson.feature(topoData, topoData.objects.countries);
  mapProjection = d3.geoNaturalEarth1().fitSize([MAP_VB_W, MAP_VB_H], mapGeojson);
  mapPathGen = d3.geoPath(mapProjection);
  mapInitialized = true;
  renderMap();
  renderMapSideDefault();
}

function colorScaleFor(){
  const style = getComputedStyle(document.documentElement);
  const land = style.getPropertyValue('--map-land').trim();
  const accent = style.getPropertyValue('--red-bright').trim();
  const maxCount = Math.max(...mapCountryCounts.values());

  return (name)=>{
    const count = mapCountryCounts.get(name);
    if(!count) return land;
    const t = Math.sqrt(count)/Math.sqrt(maxCount);
    return d3.interpolateRgb(land, accent)(Math.max(0.12, t));
  };
}

function renderMap(){
  const colorFor = colorScaleFor();
  let pathsHtml = '';

  mapGeojson.features.forEach(f=>{
    const name = f.properties.name;
    const hasData = mapCountryCounts.has(name);
    const d = mapPathGen(f);
    if(!d) return;

    const fill = hasData ? colorFor(name) : null;

    pathsHtml += `
      <path
        class="map-country ${hasData?'has-data':'no-data'}"
        data-name="${esc(name)}"
        d="${d}"
        ${fill?`style="fill:${fill}"`:''}>
        <title>${esc(name)}${hasData?` — ${fmtInt(mapCountryCounts.get(name))} concert(s)`:''}</title>
      </path>
    `;
  });

  document.getElementById('map-svg-wrap').innerHTML =
    `<svg viewBox="0 0 ${MAP_VB_W} ${MAP_VB_H}"><g id="map-g">${pathsHtml}</g></svg>`;

  document.querySelectorAll('#map-svg-wrap .map-country.has-data').forEach(el=>{
    el.addEventListener('click', ()=>{
      const name = el.dataset.name;
      const feature = mapGeojson.features.find(f=>f.properties.name===name);
      selectMapCountry(feature);
    });
  });
}

function selectMapCountry(feature){
  mapSelectedFeature = feature;
  const name = feature.properties.name;

  document.querySelectorAll('#map-svg-wrap .map-country').forEach(el=>{
    el.classList.toggle('selected', el.dataset.name===name);
  });

  const [[x0,y0],[x1,y1]] = mapPathGen.bounds(feature);
  const bw = Math.max(1, x1-x0);
  const bh = Math.max(1, y1-y0);
  const scale = Math.min(8, 0.85 / Math.max(bw/MAP_VB_W, bh/MAP_VB_H));
  const cx = (x0+x1)/2;
  const cy = (y0+y1)/2;
  const tx = MAP_VB_W/2 - scale*cx;
  const ty = MAP_VB_H/2 - scale*cy;

  const g = document.getElementById('map-g');
  g.style.transition = 'transform .5s cubic-bezier(.2,.7,.3,1)';
  g.style.transformOrigin = '0 0';
  g.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`;

  document.querySelectorAll('#map-svg-wrap .map-country').forEach(el=>{
    el.style.strokeWidth = (0.5/scale)+'px';
  });

  document.getElementById('map-current').textContent = `Vue : ${name}`;
  renderMapSideForCountry(name);
}

document.getElementById('map-reset').addEventListener('click', ()=>{
  mapSelectedFeature = null;

  const g = document.getElementById('map-g');
  if(g){
    g.style.transform = 'translate(0px,0px) scale(1)';

    document.querySelectorAll('#map-svg-wrap .map-country').forEach(el=>{
      el.classList.remove('selected');
      el.style.strokeWidth = '0.5px';
    });
  }

  document.getElementById('map-current').textContent = 'Vue : monde entier';
  renderMapSideDefault();
});

function renderMapSideDefault(){
  document.getElementById('map-side-title').textContent = 'Pays les plus visités';

  const entries = [...mapCountryCounts.entries()].sort((a,b)=>b[1]-a[1]);
  const max = entries.length ? entries[0][1] : 1;
  const el = document.getElementById('map-side-list');

  el.innerHTML = entries.map(([name,count],i)=>`
    <li class="rank-row clickable" data-country="${esc(name)}">
      <span class="rank-idx">${String(i+1).padStart(2,'0')}</span>
      <span class="rank-main">
        <span class="rank-name">${esc(name)}</span>
        <span class="rank-bar-track">
          <span class="rank-bar-fill" style="width:${(count/max*100).toFixed(0)}%"></span>
        </span>
      </span>
      <span class="rank-count">${fmtInt(count)}</span>
    </li>
  `).join('');

  el.querySelectorAll('.rank-row').forEach(row=>{
    row.addEventListener('click', ()=>{
      const name = row.dataset.country;
      const feature = mapGeojson.features.find(f=>f.properties.name===name);
      if(feature) selectMapCountry(feature);
    });
  });
}

function renderMapSideForCountry(name){
  document.getElementById('map-side-title').textContent = `Villes — ${name}`;

  const cities = mapCountryCityCounts.get(name) || new Map();
  const entries = [...cities.entries()].sort((a,b)=>b[1]-a[1]);
  const el = document.getElementById('map-side-list');

  if(entries.length===0){
    el.innerHTML = `<div class="empty-state">Aucune ville identifiée pour ce pays.</div>`;
    return;
  }

  const max = entries[0][1];

  el.innerHTML = entries.map(([city,count],i)=>`
    <li class="rank-row clickable" data-city="${esc(city)}">
      <span class="rank-idx">${String(i+1).padStart(2,'0')}</span>
      <span class="rank-main">
        <span class="rank-name">${esc(city)}</span>
        <span class="rank-bar-track">
          <span class="rank-bar-fill" style="width:${(count/max*100).toFixed(0)}%"></span>
        </span>
      </span>
      <span class="rank-count">${fmtInt(count)}</span>
    </li>
  `).join('');

  el.querySelectorAll('.rank-row').forEach(row=>{
    row.addEventListener('click', ()=>{
      document.querySelector('button[data-tab="concerts"]').click();
      document.getElementById('f-search').value = row.dataset.city;
      applyFilters();
    });
  });
}

document.querySelector('button[data-tab="map"]').addEventListener('click', initMapOnce);

document.getElementById('theme-toggle').addEventListener('click', ()=>{
  if(mapInitialized) renderMap();
});
 
