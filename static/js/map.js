// map.js — SwissStats
//Ce fichier gère toute la logique de la page carte :
//Initialisation de la carte Leaflet
//Gestion des fonds de carte (CartoDB + WMS swisstopo)
//Chargement et affichage des tracés GPS (GeoJSON depuis PostGIS)
//Exporter les gpx
//synchro avec Strava


//Constantes

// constantes couleurs
const SPORTS = {
  Run:       { color: '#fc4c02' },
  TrailRun:  { color: '#f59e0b' },
  Ride:      { color: '#3b82f6' },
  Hike:      { color: '#16a34a' },
  Walk:      { color: '#84cc16' },
  Swim:      { color: '#06b6d4' },
  AlpineSki: { color: '#8b5cf6' },
  NordicSki: { color: '#a855f7' },
  default:   { color: '#6b7280' },
};

//noms en francais
const SPORT_FR = {
  Run:       'Course à pied',
  TrailRun:  'Trail',
  Ride:      'Vélo',
  Walk:      'Marche',
  Hike:      'Randonnée',
  Swim:      'Natation',
  AlpineSki: 'Ski alpin',
  NordicSki: 'Ski nordique',
  default:   'Autre',
};

const sp = (s) => SPORTS[s] || SPORTS.default;


//fonds de carte en utilisant wms.geo.admin.ch : un service OGC WMS public et gratuit

// Carte avec fond clair
const basemaps = {
  carto: L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '© OpenStreetMap © CARTO', maxZoom: 19,
  }),
  //carte suisse topo en couleur
  swisstopo: L.tileLayer.wms('https://wms.geo.admin.ch/', {
    layers: 'ch.swisstopo.pixelkarte-farbe', format: 'image/png',
    transparent: false, attribution: '© swisstopo', maxZoom: 20,
  }),
  //carte suisse topo en grise
  swisstopoGray: L.tileLayer.wms('https://wms.geo.admin.ch/', {
    layers: 'ch.swisstopo.pixelkarte-grau', format: 'image/png',
    transparent: false, attribution: '© swisstopo', maxZoom: 20,
  }),
};

// Initialisation de la carte avec Leaflet, centrée sur la Suisse
const map = L.map('map').setView([46.8, 8.2], 8);
basemaps.carto.addTo(map);
let currentBasemap = basemaps.carto;

// Déclarations AVANT tout le reste
let trackLayer = L.layerGroup().addTo(map);
let selected   = null;


//  Changement de fond de carte
function switchBasemap() {
  const key = document.getElementById('basemapSelect').value; // Appelé par le select "Fond de carte"
  map.removeLayer(currentBasemap); //Retire l'ancien fond et ajoute le nouveau
  currentBasemap = basemaps[key];
  currentBasemap.addTo(map);
  currentBasemap.bringToBack(); //derrière les tracés GPS

}

// Chargement des tracés
async function loadTracks() {
//Appel GET /api/tracks?year=...&sport=...
  const year  = document.getElementById('yearInput').value;
  const sport = document.getElementById('sportFilter').value;
  showLoader('Chargement des parcours…');
  trackLayer.clearLayers();
  document.getElementById('activityList').innerHTML = '';

  try {
  //Flask interroge PostgreSQL (ST_AsGeoJSON) → GeoJSON FeatureCollection
    const res   = await fetch(`/api/tracks?year=${year}${sport ? '&sport=' + sport : ''}`);
    const data  = await res.json();
    const feats = data.features || [];

    document.getElementById('countBadge').innerHTML = `<b>${feats.length}</b> parcours`;
    if (!feats.length) { hideLoader(); return; }

    const bounds = [];

    feats.forEach((f, i) => {
      const p      = f.properties;
      const style  = sp(p.sport_type);

      // PostGIS retourne [lng, lat] → Leaflet attend [lat, lng]

      const coords = f.geometry.coordinates.map(c => [c[1], c[0]]);

      // Création de la polyligne Leaflet/ PostGIS retourne [lng, lat] → Leaflet attend [lat, lng]

      const line = L.polyline(coords, { color: style.color, weight: 3, opacity: 0.8 });
      // Événements souris : sélection et survol
      line.on('click',     () => pick(i, line)); //La sidebar est peuplée avec une liste cliquable
      line.on('mouseover', function() { this.setStyle({ weight: 5, opacity: 1 }); });
      // Ne réinitialise pas si c'est la ligne sélectionnée
      line.on('mouseout',  function() { if (selected !== this) this.setStyle({ weight: 3, opacity: 0.8 }); });
      // Popup avec les détails de l'activité
      line.bindPopup(buildPopup(p), { maxWidth: 240 });
      trackLayer.addLayer(line);
      coords.forEach(c => bounds.push(c));

//Élément dans la sidebar
      const d    = new Date(p.date).toLocaleDateString('fr-CH', { day: '2-digit', month: 'short' });
      const item = document.createElement('div');
      item.className = 'activity-item';
      item.id = `a${i}`;
      item.innerHTML = `
        <span class="sport-tag" style="background:${style.color}18;color:${style.color}">
          ${SPORT_FR[p.sport_type] || SPORT_FR.default}
        </span>
        <div class="act-name">${p.name || 'Sans nom'}</div>
        <div class="act-meta">${d} · ${p.distance_km} km${p.elevation_m ? ` · ↑ ${p.elevation_m}m` : ''}</div>`;
        // Clic sur la sidebar → ouvre le popup et centre la carte sur le tracé

      item.onclick = () => {
        line.openPopup();
        pick(i, line);
        map.fitBounds(line.getBounds(), { padding: [30, 30] });
      };
      document.getElementById('activityList').appendChild(item);
    });

    // Zoom automatique pour afficher tous les tracés
    if (bounds.length) map.fitBounds(bounds, { padding: [20, 20] });
  } catch (e) {
    console.error(e);
    alert('Erreur de chargement.');
  }
  hideLoader();
}

// ── Sélection d'un tracé

function pick(i, line) {
  // Réinitialise l'ancien tracé sélectionné
  if (selected) selected.setStyle({ weight: 3, opacity: 0.8 });
  document.querySelectorAll('.activity-item.active').forEach(el => el.classList.remove('active'));
  // Applique la sélection au nouveau tracé
  selected = line;
  line.setStyle({ weight: 5, opacity: 1 });
  // Synchronise avec la sidebar
  const el = document.getElementById(`a${i}`);
  el?.classList.add('active');
  el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Popup de détail

function buildPopup(p) {
  const dur = p.moving_time_s // Formatage de la durée en heures et minutes

    ? `${Math.floor(p.moving_time_s / 3600)}h${String(Math.floor(p.moving_time_s % 3600 / 60)).padStart(2, '0')}`
    : '—';
  const d = new Date(p.date).toLocaleDateString('fr-CH', { day: '2-digit', month: 'long', year: 'numeric' });
  // Construction du tableau de stats — filtre les valeurs nulles/0

  const stats = [
    ['Distance',  `${p.distance_km} km`],
    ['Durée',     dur],
    p.elevation_m && ['Dénivelé', `${p.elevation_m} m`],
    p.calories    && ['Calories',  `${p.calories} kcal`],
    p.avg_speed   && ['Vitesse',   `${p.avg_speed} km/h`],
    p.heartrate   && ['FC moy.',   `${p.heartrate} bpm`],
  ].filter(Boolean);

  return `
    <div class="pop-title">${p.name || 'Activité'}</div>
    <div class="pop-date">${d}</div>
    <div class="pop-grid">
      ${stats.map(([l, v]) => `<div class="pop-stat"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('')}
    </div>
    <a class="pop-gpx" href="/api/gpx/${p.id}" download>⬇ Exporter GPX</a>`;
}

// Sync Strava
async function syncActivities() {
  const year = document.getElementById('yearInput').value;
  showLoader('Connexion à Strava…');

  // Lance le job de sync côté serveur
  let job_id;
  try {
    const res  = await fetch(`/sync?year=${year}`);
    const data = await res.json();
    if (data.error) { hideLoader(); alert('Erreur : ' + data.error); return; }
    job_id = data.job_id; // Identifiant unique du job pour le suivi

  } catch (e) {
    hideLoader();
    alert('Impossible de démarrer la sync : ' + e.message); //afficher les messages d'erreur
    return;
  }
//Montrer la progression toutes les secondes

  const interval = setInterval(async () => {
    try {
      const r = await fetch(`/sync/status?job_id=${job_id}`);
      const d = await r.json();
       // Met à jour le texte de statut
      document.getElementById('loaderSub').textContent = d.msg || '';
      if (d.total > 0) { // Affiche la barre de progression dès qu'on connaît le total
        document.getElementById('progTrack').style.display = 'block';
        document.getElementById('progBar').style.width     = (d.pct || 0) + '%';
        document.getElementById('progLabel').textContent   = `${d.done} / ${d.total} activités`;
      }
      // Gestion des cas terminaux
      if (d.error)    { clearInterval(interval); hideLoader(); alert('Erreur : ' + d.error); }
      if (d.finished) { clearInterval(interval); setTimeout(() => { hideLoader(); loadTracks(); }, 800); }
      // Petite pause avant de recharger les tracés pour laisser la DB se stabiliser

    } catch {
      clearInterval(interval); hideLoader(); alert('Erreur de synchronisation.');
    }
  }, 1000);
}

// Loader
//Affiche l'overlay de chargement avec un message personnalisé.

function showLoader(msg) {
  document.getElementById('loaderSub').textContent   = msg;
  document.getElementById('progTrack').style.display = 'none';
  document.getElementById('progBar').style.width     = '0%';
  document.getElementById('progLabel').textContent   = '';
  document.getElementById('loader').classList.add('active');
}
/** Masque l'overlay de chargement */
function hideLoader() {
  document.getElementById('loader').classList.remove('active');
}

// Charge les tracés de l'année affichée au démarrage de la page
loadTracks();
