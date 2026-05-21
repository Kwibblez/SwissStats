// map.js

const SPORTS = {
  Run:       { color: '#fc4c02', emoji: '🏃' },
  Ride:      { color: '#3b82f6', emoji: '🚴' },
  Hike:      { color: '#22c55e', emoji: '🥾' },
  Walk:      { color: '#a3e635', emoji: '🚶' },
  Swim:      { color: '#06b6d4', emoji: '🏊' },
  AlpineSki: { color: '#a78bfa', emoji: '⛷️' },
  NordicSki: { color: '#c084fc', emoji: '🎿' },
  Rowing:    { color: '#f59e0b', emoji: '🚣' },
  default:   { color: '#7a8098', emoji: '🏅' },
};
const sp = (s) => SPORTS[s] || SPORTS.default;

const map = L.map('map').setView([46.5, 8.0], 8);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '© OpenStreetMap © CARTO', maxZoom: 19,
}).addTo(map);

let trackLayer = L.layerGroup().addTo(map);
let selected   = null;

async function loadTracks() {
  const year  = document.getElementById('yearInput').value;
  const sport = document.getElementById('sportFilter').value;
  showLoader('Récupération des tracés…', '🗺');
  trackLayer.clearLayers();
  document.getElementById('activityList').innerHTML = '';

  try {
    const res   = await fetch(`/api/tracks?year=${year}${sport ? '&sport='+sport : ''}`);
    const data  = await res.json();
    const feats = data.features || [];

    document.getElementById('countBadge').innerHTML = `<b>${feats.length}</b> parcours`;
    if (!feats.length) { hideLoader(); return; }

    const bounds = [];
    feats.forEach((f, i) => {
      const p      = f.properties;
      const style  = sp(p.sport_type);
      const coords = f.geometry.coordinates.map(c => [c[1], c[0]]);

      const line = L.polyline(coords, { color: style.color, weight: 2.5, opacity: 0.7 });
      line.on('click',     () => pick(i, line));
      line.on('mouseover', function() { this.setStyle({ weight: 4, opacity: 1 }); });
      line.on('mouseout',  function() { if (selected !== this) this.setStyle({ weight: 2.5, opacity: 0.7 }); });
      line.bindPopup(buildPopup(p), { maxWidth: 240 });
      trackLayer.addLayer(line);
      coords.forEach(c => bounds.push(c));

      const d    = new Date(p.date).toLocaleDateString('fr-CH', { day:'2-digit', month:'short' });
      const item = document.createElement('div');
      item.className = 'activity-item';
      item.id = `a${i}`;
      item.innerHTML = `
        <span class="sport-tag" style="background:${style.color}20;color:${style.color}">${style.emoji} ${p.sport_type}</span>
        <div class="act-name">${p.name || 'Sans nom'}</div>
        <div class="act-meta">
          <span>${d}</span><span>${p.distance_km} km</span>
          ${p.elevation_m ? `<span>↑ ${p.elevation_m}m</span>` : ''}
        </div>`;
      item.onclick = () => {
        line.openPopup();
        pick(i, line);
        map.fitBounds(line.getBounds(), { padding: [30, 30] });
      };
      document.getElementById('activityList').appendChild(item);
    });

    if (bounds.length) map.fitBounds(bounds, { padding: [20, 20] });
  } catch(e) { console.error(e); alert('Erreur de chargement.'); }
  hideLoader();
}

function pick(i, line) {
  if (selected) selected.setStyle({ weight: 2.5, opacity: 0.7 });
  document.querySelectorAll('.activity-item.active').forEach(el => el.classList.remove('active'));
  selected = line;
  line.setStyle({ weight: 5, opacity: 1 });
  const el = document.getElementById(`a${i}`);
  el?.classList.add('active');
  el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function buildPopup(p) {
  const dur = p.moving_time_s
    ? `${Math.floor(p.moving_time_s/3600)}h${String(Math.floor(p.moving_time_s%3600/60)).padStart(2,'0')}`
    : '—';
  const d = new Date(p.date).toLocaleDateString('fr-CH', { day:'2-digit', month:'long', year:'numeric' });
  const stats = [
    ['Distance', `${p.distance_km} km`],
    ['Durée', dur],
    p.elevation_m && ['Dénivelé', `${p.elevation_m} m`],
    p.calories    && ['Calories', `${p.calories} kcal`],
    p.avg_speed   && ['Vitesse', `${p.avg_speed} km/h`],
    p.heartrate   && ['FC moy.', `${p.heartrate} bpm`],
  ].filter(Boolean);

  return `
    <div class="pop-title">${p.name || 'Activité'}</div>
    <div class="pop-date">${d}</div>
    <div class="pop-grid">
      ${stats.map(([l,v]) => `<div class="pop-stat"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('')}
    </div>
    <a class="pop-gpx" href="/api/gpx/${p.id}" download>⬇ Exporter GPX</a>`;
}

function syncActivities() {
  const year = document.getElementById('yearInput').value;
  showLoader('Connexion à Strava…', '🔄');
  const src = new EventSource(`/sync?year=${year}`);
  src.onmessage = (e) => {
    const d = JSON.parse(e.data);
    document.getElementById('loaderSub').textContent = d.msg || '';
    if (d.total > 0) {
      document.getElementById('progTrack').style.display = 'block';
      document.getElementById('progBar').style.width     = (d.pct || 0) + '%';
      document.getElementById('progLabel').textContent   = `${d.done} / ${d.total} activités`;
    }
    if (d.finished) { src.close(); setTimeout(() => { hideLoader(); loadTracks(); }, 600); }
  };
  src.onerror = () => { src.close(); hideLoader(); alert('Erreur de synchronisation.'); };
}

function showLoader(msg, icon = '⚡') {
  document.getElementById('loaderIcon').textContent  = icon;
  document.getElementById('loaderSub').textContent   = msg;
  document.getElementById('progTrack').style.display = 'none';
  document.getElementById('progBar').style.width     = '0%';
  document.getElementById('progLabel').textContent   = '';
  document.getElementById('loader').classList.add('active');
}
function hideLoader() { document.getElementById('loader').classList.remove('active'); }

loadTracks();
