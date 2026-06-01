/**
 * Ce fichier gère l'affichage de la page statistiques :
 *   - Chargement des données depuis l'API Flask (/api/stats)
 *   - Affichage des totaux annuels (distance, durée, dénivelé, calories, FC)
 *   - Section "fun facts" avec comparaisons suisses
 *   - Graphique à barres : distance par mois
 *   - Graphique donut : répartition par sport
 *   - Tableau récapitulatif par sport
 *
 * HEIG-VD 2026 — Fardel, Perroud, Smith
 */

// Constantes

/* Noms des mois en français pour l'axe X du graphique mensuel */
const MONTHS = ['Jan','Fév','Mar','Avr','Mai','Jun','Jul','Aoû','Sep','Oct','Nov','Déc'];

/*Couleurs associées à chaque type de sport Strava et utilisées dans le graphique et le tableau.
 */
const COLORS = {
  Run:       '#fc4c02',
  Ride:      '#3b82f6',
  Hike:      '#16a34a',
  Walk:      '#84cc16',
  Swim:      '#06b6d4',
  AlpineSki: '#8b5cf6',
  NordicSki: '#a855f7',
  TrailRun:  '#f59e0b',
  default:   '#6b7280',
};

/*Traductions françaises des types de sport Strava.
Les types sont les valeurs renvoyées par l'API Strava (en anglais).
 */
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

//Retourne le nom français d'un sport, ou le nom original si inconnu.
const sportName = (s) => SPORT_FR[s] || s;

/* Formate un nombre avec séparateur de milliers suisse (apostrophe).
Retourne '—' si la valeur est null ou undefined.
 */
const fmt = (n) => n == null ? '—' : Number(n).toLocaleString('fr-CH');

// Références aux instances Chart.js (pour les détruire avant recréation)
let cMonth = null;
let cSport = null;


// Navigation entre les années

/*
 Incrémente ou décrémente l'année affichée et recharge les statistiques.
 Appelé par les boutons ◀ et ▶ dans la barre de navigation.
 @param {number} d - Delta à appliquer (+1 ou -1)
 */
function changeYear(d) {
  const el = document.getElementById('yearInput');
  el.value = +el.value + d;
  loadStats();
}


// Chargement des données

/*
 Récupère les statistiques de l'année sélectionnée depuis l'API Flask.
 Affiche un message de chargement pendant la requête.
 En cas d'erreur réseau ou serveur, affiche un message d'erreur.
 */
async function loadStats() {
  const year = document.getElementById('yearInput').value;

  // Affiche l'indicateur de chargement
  document.getElementById('content').innerHTML =
    `<div class="empty">Chargement de ${year}…</div>`;

  try {
    const res = await fetch(`/api/stats?year=${year}`);
    render(await res.json());
  } catch {
    document.getElementById('content').innerHTML =
      '<div class="empty">Erreur de chargement.</div>';
  }
}


//Rendu de la page

/*
 Construit et affiche tout le contenu de la page statistiques.
  Appelé une fois les données reçues de l'API.

  @param {Object} data - Réponse de /api/stats contenant :
  - data.year      : année
  - data.totals    : totaux agrégés (distance, temps, calories…)
  - data.fun       : comparaisons fun (vaches, lac Léman…)
  - data.by_sport  : stats par type de sport
  - data.by_month  : stats par mois
 */
function render(data) {
  const t   = data.totals;
  const fun = data.fun;

  // Calcul de la durée totale en heures et minutes
  const km  = Math.round(t.total_m / 1000);
  const h   = Math.floor(t.total_seconds / 3600);
  const min = Math.floor((t.total_seconds % 3600) / 60);

  // Injection du HTML principal dans le conteneur
  document.getElementById('content').innerHTML = `
    <div class="section">
      <div class="section-title">Résumé ${data.year}</div>
      <div class="totals-grid">
        <div class="stat-card"><div class="val">${fmt(t.nb_activities)}</div><div class="unit">activités</div></div>
        <div class="stat-card"><div class="val">${fmt(km)}</div><div class="unit">km parcourus</div></div>
        <div class="stat-card"><div class="val">${h}h${String(min).padStart(2,'0')}</div><div class="unit">en mouvement</div></div>
        <div class="stat-card"><div class="val">${fmt(Math.round(t.total_elevation))}</div><div class="unit">m dénivelé</div></div>
        <div class="stat-card"><div class="val">${fmt(Math.round(t.total_calories))}</div><div class="unit">kcal brûlées</div></div>
        ${t.avg_heartrate ? `<div class="stat-card"><div class="val">${Math.round(t.avg_heartrate)}</div><div class="unit">bpm moyen</div></div>` : ''}
      </div>
    </div>

    <div class="section">
      <div class="section-title">C'est l'équivalent de…</div>
      <div class="fun-grid">
        <div class="fun-card"><div class="fun-icon"><img src="static/figures/imgs/vache.png"></div><div><div class="fun-num">${fmt(fun.vaches)}</div><div class="fun-lbl">vaches bout à bout (Ô la vache !)</div><div class="fun-desc">Une vache ≈ 2.4 m</div></div></div>
        <div class="fun-card"><div class="fun-icon"><img src="static/figures/imgs/lacLeman.jpg"></div><div><div class="fun-num">${fun.lac_leman}×</div><div class="fun-lbl">le tour du lac Léman</div><div class="fun-desc">170 km de tour complet</div></div></div>
        <div class="fun-card"><div class="fun-icon"><img src="static/figures/imgs/cervin.jpeg"></div><div><div class="fun-num">${fun.cervin}×</div><div class="fun-lbl">l'altitude du Cervin</div><div class="fun-desc">${fmt(Math.round(t.total_elevation))} m de dénivelé en total</div></div></div>
        <div class="fun-card"><div class="fun-icon"><img src="static/figures/imgs/fondue.jpg"></div><div><div class="fun-num">${fmt(fun.fondues)}</div><div class="fun-lbl">fondues brûlées</div><div class="fun-desc">≈ 800 kcal par fondue</div></div></div>
        <div class="fun-card"><div class="fun-icon"><img src="static/figures/imgs/country.png"></div><div><div class="fun-num">${fun.swissTotal}%</div><div class="fun-lbl">de la Suisse parcourue</div><div class="fun-desc">Bien joué !</div></div></div>
        <div class="fun-card"><div class="fun-icon"><img src="static/figures/imgs/SwissCucko.webp"></div><div><div class="fun-num">${fun.heures} heures</div><div class="fun-lbl">de sport au total</div><div class="fun-desc">Soit ${(fun.heures / 24).toFixed(1)} jours complets</div></div></div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Évolution</div>
      <div class="charts-grid">
        <div class="chart-card"><h3>Distance par mois (km)</h3><canvas id="cMonth" height="160"></canvas></div>
        <div class="chart-card"><h3>Répartition par sport</h3><canvas id="cSport" height="160"></canvas></div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Par sport</div>
      <div class="chart-card">
        <table class="sport-table">
          <thead><tr><th>Sport</th><th>Activités</th><th>Distance</th><th>Calories</th></tr></thead>
          <tbody id="sportBody"></tbody>
        </table>
      </div>
    </div>`;

  // Tableau par sport
  // Rempli avec les données de l'API
  data.by_sport.forEach(s => {
    const c    = COLORS[s.sport_type] || COLORS.default;
    const name = sportName(s.sport_type);
    document.getElementById('sportBody').innerHTML +=
      `<tr>
        <td><span class="sport-dot" style="background:${c}"></span>${name}</td>
        <td>${s.nb}</td>
        <td>${s.km} km</td>
        <td>${fmt(s.kcal)} kcal</td>
      </tr>`;
  });

  //Graphique à barres : distance par mois
  // Construit un tableau de 12 valeurs (une par mois)
  // Les mois sans activité restent à 0
  const monthVals = new Array(12).fill(0);
  data.by_month.forEach(m => { monthVals[m.month - 1] = +m.km || 0; });

  // Détruit l'ancienne instance avant d'en créer une nouvelle
  // (évite les erreurs lors du changement d'année)
  if (cMonth) cMonth.destroy();
  cMonth = new Chart(document.getElementById('cMonth'), {
    type: 'bar',
    data: {
      labels: MONTHS,
      datasets: [{
        data:            monthVals,
        backgroundColor: '#fc4c0220',  // Orange Strava transparent
        borderColor:     '#fc4c02',
        borderWidth:     2,
        borderRadius:    4,
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },  // Pas de légende pour le bar chart
      scales: {
        x: { ticks: { color: '#6b7280', font: { size: 11 } }, grid: { color: '#e2e4e9' } },
        y: { ticks: { color: '#6b7280', font: { size: 11 } }, grid: { color: '#e2e4e9' } },
      }
    }
  });

  // Graphique donut : répartition par sport
  // Chaque segment représente les km parcourus pour un sport
  if (cSport) cSport.destroy();
  cSport = new Chart(document.getElementById('cSport'), {
    type: 'doughnut',
    data: {
      labels: data.by_sport.map(s => sportName(s.sport_type)),
      datasets: [{
        data:            data.by_sport.map(s => +s.km || 0),
        backgroundColor: data.by_sport.map(s => COLORS[s.sport_type] || COLORS.default),
        borderWidth:     2,
        borderColor:     '#ffffff',  // Séparateur blanc entre les segments
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#6b7280', font: { size: 11 }, padding: 12 }
        }
      }
    }
  });
}

// Initialisation
// Charge les statistiques de l'année affichée au chargement de la page
loadStats();
