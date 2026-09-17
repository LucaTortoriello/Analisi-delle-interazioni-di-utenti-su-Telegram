<template>
  <div class="dashboard">
    <!-- Header --> 
    <div class="dashboard-header">
      <header class="app-page-header">
        <div>
          <span class="app-eyebrow">Analysis overview</span>
          <h1 class="page-title">Dashboard</h1>
          <p class="app-page-description">Una vista sintetica su utenti, conversazioni e attività raccolte.</p>
        </div>
      </header>
      <div class="kpis">
        <!-- KPI -->
        <router-link to="/utenti" class="kpi-card">
          <div class="kpi-icon">
            <svg xmlns="http://www.w3.org/2000/svg" class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
          </div>
          <div>
            <div class="kpi-title">Totale Utenti</div>
            <div class="kpi-value">{{ stats.utenti_totali ?? '—' }}</div>
          </div>
        </router-link>

        <router-link to="/chat" class="kpi-card">
          <div class="kpi-icon">
            <svg xmlns="http://www.w3.org/2000/svg" class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
          </div>
          <div>
            <div class="kpi-title">Chat Analizzate</div>
            <div class="kpi-value">{{ stats.chat_totali ?? '—' }}</div>
          </div>
        </router-link>

        <router-link to="/messaggi" class="kpi-card">
          <div class="kpi-icon">
            <svg xmlns="http://www.w3.org/2000/svg" class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M22 2L11 13"/>
              <path d="M22 2l-7 20-4-9-9-4 20-7z"/>
            </svg>
          </div>
          <div>
            <div class="kpi-title">Messaggi Totali</div>
            <div class="kpi-value">{{ stats.messaggi_totali ?? '—' }}</div>
          </div>
        </router-link>
      </div>
    </div>

    <!-- Layout principale -->
    <div class="main-layout">
      <!-- Sidebar sinistra -->
      <aside class="sidebar">
        <!-- Categorie -->
        <div class="card categories">
          <h3>Categorie Chat</h3>
          <ul v-if="categorie.length">
            <li v-for="c in categorie" :key="c.categoria_chat">
              <router-link
                :to="{ path: '/chat', query: { categoria: c.categoria_chat } }"
                class="category-item"
              >
                <span class="cat-name">{{ c.categoria_chat || 'Non classificata' }}</span>
                <span class="cat-count">{{ c.totale }}</span>
              </router-link>
            </li>
          </ul>
          <p v-else>Nessuna categoria disponibile</p>
        </div>
      </aside>

      <!-- Contenuto principale -->
      <main class="content">
        <!-- Grafico -->
        <div class="card big-chart">
          <h3>Attività ultimi 7 giorni</h3>
          <div v-if="error" class="error">Errore dashboard: {{ error }}</div>
          <div v-else>
            <canvas ref="chartEl"></canvas>
          </div>
        </div>

        <!-- Utenti più attivi (sotto al grafico) -->
        <div class="card" style="margin-top: 2rem;">
          <h3>Utenti più attivi</h3>
          <ul>
            <li v-for="u in topUtenti" :key="u.id">
              <router-link :to="{ name: 'UtenteDettaglio', params: { userId: u.id }}">
                {{ u.nome }} — <b>{{ u.messaggi }}</b> messaggi
              </router-link>
            </li>
          </ul>
        </div>

        <!-- Chat più attive (ancora più sotto) -->
        <div class="card" style="margin-top: 2rem;">
          <h3>Chat più attive</h3>
          <ul>
            <li v-for="c in topChat" :key="c.id">
              <router-link :to="{ name: 'Messaggi', params: { chatId: c.id }}">
                {{ c.nome }} — <b>{{ c.messaggi }}</b> messaggi
              </router-link>
            </li>
          </ul>
        </div>
      </main>
    </div>
  </div>
</template>

<script>
import { onMounted, ref } from "vue";
import Chart from "chart.js/auto";

export default {
  name: "Dashboard",
  setup() {
    const stats = ref({ utenti_totali: 0, chat_totali: 0, messaggi_totali: 0 });
    const categorie = ref([]);
    const labels = ref([]);
    const counts = ref([]);
    const activeUsers = ref([]);
    const error = ref("");
    const chartEl = ref(null);
    let chart = null;

    const topUtenti = ref([]);
    const topChat = ref([]);

    const fetchStats = async () => {
      const res = await fetch("http://127.0.0.1:5000/api/statistiche");
      const json = await res.json();
      if (json.status === "success") stats.value = json;
    };

    const fetchActivity = async () => {
      const res = await fetch("http://127.0.0.1:5000/api/attivita?days=7");
      const json = await res.json();
      if (json.status !== "success") throw new Error(json.message || "Bad response");
      labels.value = json.labels || [];
      counts.value = json.counts || [];
      activeUsers.value = json.active_users || [];
    };

    const fetchCategorie = async () => {
      const res = await fetch("http://127.0.0.1:5000/api/chat_per_categoria");
      const json = await res.json();
      if (json.status === "success") categorie.value = json.data;
    };

    const fetchTopUtenti = async () => {
      const res = await fetch("http://127.0.0.1:5000/api/top_utenti?limit=5");
      const json = await res.json();
      if (json.status === "success") {
        topUtenti.value = json.data.map(u => ({
          id: u.id,
          nome: u.nome || u.username || `Utente ${u.id}`,
          messaggi: u.messaggi
        }));
      }
    };

    const fetchTopChat = async () => {
  const res = await fetch("http://127.0.0.1:5000/api/top_chat?limit=5");
  const json = await res.json();
  if (json.status === "success") {
    topChat.value = json.data.map(c => ({
      id: c.id_chat,
      nome: c.nome_chat_tradotto || c.nome_chat,
      messaggi: c.messaggi
    }));
  }
};


    const draw = () => {
      if (!chartEl.value) return;
      if (chart) { chart.destroy(); chart = null; }
      if (!labels.value.length) return;

      const ctx = chartEl.value.getContext("2d");
      const gradient = ctx.createLinearGradient(0, 0, 0, 400);
      gradient.addColorStop(0, "rgba(30,79,209,0.4)");
      gradient.addColorStop(1, "rgba(30,79,209,0.05)");

      chart = new Chart(ctx, {
        type: "line",
        data: {
          labels: labels.value,
          datasets: [
            {
              label: "Messaggi",
              data: counts.value,
              fill: true,
              borderColor: "#1e4fd1",
              backgroundColor: gradient,
              borderWidth: 2,
              pointRadius: 4,
              pointBackgroundColor: "#1e4fd1",
              tension: 0.35
            },
            {
              label: "Utenti attivi",
              data: activeUsers.value,
              borderColor: "#64748b",
              borderDash: [6, 4],
              borderWidth: 2,
              pointRadius: 4,
              pointBackgroundColor: "#64748b",
              fill: false,
              tension: 0.35
            }
          ]
        },
        options: { responsive: true, maintainAspectRatio: false }
      });
    };

    onMounted(async () => {
  console.time("dashboard-load"); // debug: misura tempi caricamento
  try {
    // Eseguiamo tutte le richieste in parallelo
    await Promise.all([
      fetchStats(),
      fetchActivity(),
      fetchCategorie(),
      fetchTopUtenti(),
      fetchTopChat()
    ]);

    console.timeEnd("dashboard-load"); // stampa tempo totale
    draw(); // disegna grafico solo dopo che tutto è arrivato
  } catch (e) {
    console.error(e);
    error.value = e?.message || "Failed to fetch";
  }
});


    return { stats, categorie, labels, counts, activeUsers, error, chartEl, topUtenti, topChat };
  }
};
</script>

<style scoped>
.dashboard { 
  padding: 2rem clamp(0.25rem, 1.5vw, 1.75rem) 3rem; 
  width: 100%; 
  max-width: 1800px;
  margin: 0 auto;
}

.dashboard-header { 
  display: flex; 
  flex-direction: column; 
  gap: 0;
  margin-bottom: 1rem;
}

.kpis { 
  display: flex; 
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}
.kpi-card {
  display: flex; 
  align-items: center; 
  gap: 0.85rem;
  min-height: 82px;
  padding: 0.9rem 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 13px;
  background: #fff;
  text-decoration: none; 
  color: inherit;
  box-shadow: 0 1px 2px rgba(15,23,42,0.03);
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}
.kpi-card:hover { 
  transform: translateY(-2px);
  border-color: #c7d2fe;
  box-shadow: 0 8px 20px rgba(15,23,42,0.07);
}
.kpi-icon { 
  width: 38px; 
  height: 38px; 
  border-radius: 10px; 
  background: #eef2ff;
  display: flex; 
  align-items: center; 
  justify-content: center; 
  color: #4f46e5;
}
.kpi-icon .icon { width: 21px; height: 21px; }
.kpi-title { 
  font-size: 0.8rem; 
  font-weight: 600; 
  text-transform: uppercase; 
  color: #64748b;
  letter-spacing: 0.03em;
}
.kpi-value { 
  font-size: 1.35rem;
  font-weight: 700; 
  color: var(--color-primary); 
}

/* Layout principale: sidebar + contenuto */
.main-layout {
  display: grid;
  grid-template-columns: 280px 1fr; /* sidebar + contenuto */
  gap: 1rem;
  width: 100%;
  max-width: 100%;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.content {
  width: 100%;
}

/* Card */
.card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 1.25rem 1.5rem;
  box-shadow: 0 4px 18px rgba(15,23,42,0.045);
}
.card h3 { 
  margin-bottom: 1rem; 
  font-size: 1.2rem; 
  font-weight: 600; 
  color: var(--color-text); 
}

.categories ul { 
  list-style: none; 
  padding: 0; 
  margin: 0; 
}
.category-item { 
  display: flex; 
  justify-content: space-between; 
  padding: 0.6rem 0; 
  border-bottom: 1px solid #edf1f6;
  color: #1e293b; 
  text-decoration: none; 
}
.category-item:hover { 
  color: var(--color-primary); 
}
.cat-count { 
  min-width: 28px;
  padding: 0.05rem 0.4rem;
  border-radius: 999px;
  background: #eef2ff;
  color: #4f46e5;
  font-size: 0.75rem;
  font-weight: 800;
  text-align: center;
}

/* Grafico grande */
.big-chart {
  min-height: 520px;
}
canvas { 
  width: 100% !important; 
  height: 520px !important; 
}

/* Responsive */
@media (max-width: 1100px) {
  .main-layout {
    grid-template-columns: 1fr;
  }
  .sidebar { order: 2; }
}
@media (max-width: 768px) {
  .dashboard { padding: 1rem 0 2rem; }
  .kpis { grid-template-columns: 1fr; }
}
</style>
