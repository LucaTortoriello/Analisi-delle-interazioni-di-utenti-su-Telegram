<template>
  <div v-cloak class="app-section messages-page">
    <header class="app-page-header messages-header">
      <div>
        <span class="app-eyebrow">Content intelligence</span>
        <h1 class="page-title">
          Messaggi
          <span v-if="chatId && (chatInfo.nome_chat_tradotto || chatInfo.nome_chat)">
            — {{ chatInfo.nome_chat_tradotto || chatInfo.nome_chat }}
          </span>
        </h1>
        <p class="app-page-description">Esplora contenuti, autori, intervalli temporali e collegamenti tra conversazioni.</p>
      </div>
      <button class="btn-back" @click="tornaAllaVistaIniziale">
        <span class="icon">⟵</span> Vista iniziale
      </button>
    </header>

    <div v-if="chatId && chatInfo.id_chat" class="card chat-info">
      <div class="chat-info-header">
        <div class="avatar-wrapper">
          <img
            v-if="chatInfo.foto_url"
            :src="chatInfo.foto_url"
            class="avatar-xl"
            @error="chatInfo.foto_url = ''"
          >
        </div>
        <div class="meta">
          
          <div class="scan-controls">
              <button 
                  class="btn btn-scan"
                  :disabled="isImporting"
                  @click="lanciaScansione('incrementale')"
                  :title="isImporting ? 'Scansione in corso...' : 'Avvia scansione incrementale'"
              >
                  <span v-if="!isImporting">Aggiorna Messaggi (Incrementale)</span>
                  <span v-else>⏳ Scansione in corso...</span>
              </button>

              <div v-if="isImporting || importStatusMsg" class="import-status-bar">
                  <span class="status-icon" :class="{ 'icon-spin': isImporting, 'icon-done': !isImporting && importStatusMsg.startsWith('✅') }">
                      {{ isImporting ? '🔄' : (importStatusMsg.startsWith('✅') ? '✅' : (importStatusMsg.startsWith('❌') ? '❌' : 'ℹ️')) }}
                  </span>
                  <span class="status-text">{{ importStatusMsg }}</span>
              </div>
          </div>
          <div class="title-line">
            <h2 class="chat-name">{{ chatInfo.nome_chat_tradotto || chatInfo.nome_chat }}</h2>
            <span class="pill" :class="chatInfo.tipo === 'canale' ? 'pill-blue' : 'pill-green'">
              {{ chatInfo.tipo || '—' }}
            </span>
          </div>

          <div class="sub-line">
            <span v-if="chatInfo.username" class="muted">@{{ chatInfo.username }}</span>
            <span class="muted">• ID Chat: <strong>{{ chatInfo.id_chat }}</strong></span>
            <span class="muted">• Categoria:
              <strong>{{ chatInfo.categoria_chat || 'Non classificata' }}</strong>
            </span>
            <span class="muted">• Utenti attivi: <strong>{{ chatInfo.utenti_attivi ?? 0 }}</strong></span>
            <span class="muted">• Messaggi: <strong>{{ chatInfo.messaggi_totali ?? 0 }}</strong></span>
          </div>

          <div class="chat-admins" v-if="chatInfo.admins && chatInfo.admins.length > 0">
            <div class="admin-header">
              <span class="admin-icon" title="Amministratori">🛡️</span>
              <span class="admin-label">Amministratori</span>
              <span class="admin-count">{{ chatInfo.admins.length }}</span>
            </div>
            
            <div class="admin-list">
              <span 
                v-for="(admin, index) in chatInfo.admins.slice(0, 3)" 
                :key="admin.id" 
                class="admin-badge"
                @click="openUser(admin.id)"
                :title="'ID: ' + admin.id"
              >
                <span class="admin-avatar">{{ (admin.nome || admin.username || 'A')[0].toUpperCase() }}</span>
                <span class="admin-name">{{ admin.nome || admin.username || 'Admin' }}</span>
              </span>
              
              <div v-if="chatInfo.admins.length > 3" class="admin-dropdown">
                <button class="admin-more-btn" @click="toggleAdminDropdown">
                  <span>+{{ chatInfo.admins.length - 3 }}</span>
                  <span class="dropdown-arrow">▼</span>
                </button>
                <div v-if="showAdminDropdown" class="admin-dropdown-menu">
                  <span 
                    v-for="admin in chatInfo.admins.slice(3)" 
                    :key="admin.id" 
                    class="admin-dropdown-item"
                    @click="openUser(admin.id)"
                    :title="'ID: ' + admin.id"
                  >
                    <span class="admin-avatar">{{ (admin.nome || admin.username || 'A')[0].toUpperCase() }}</span>
                    <span class="admin-name">{{ admin.nome || admin.username || 'Admin' }}</span>
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div class="sub-line small" v-if="chatInfo.prima_data || chatInfo.ultima_data">
            <span class="muted">
              Attività: {{ formatDate(chatInfo.prima_data) || '—' }} →
              {{ formatDate(chatInfo.ultima_data) || '—' }}
            </span>
          </div>

          <div v-if="chatInfo.ultima_scansione || chatInfo.messaggi_totali === 0" class="chat-status">

  <div v-if="chatInfo.messaggi_totali === 0" class="status-inactive">

    <span class="dot orange"></span>

    <span>⚠️ Nessun messaggio importato - verifica accesso al gruppo</span>

  </div>

  <div v-else-if="isGroupActive" class="status-active">

    <span class="dot"></span>

    <span>All'ultima scansione il gruppo risulta ancora attivo</span>

  </div>

  <div v-else class="status-inactive">

    <span class="dot orange"></span>

    <span>Attenzione: il gruppo potrebbe non essere più attivo</span>

  </div>

</div>
        </div>
      </div>
    </div>

    <div class="user-activity-banner card">
      <div class="ua-left">
        <div>
          <strong>Attività utenti</strong>
        </div>
      </div>
    </div>

    <div class="card search-bar" v-if="!chatId && !userId">
      <div class="filters" @keyup.enter="!loading && doSearch()">
        
        <div class="keyword-search">
          <select v-model="selectedKeyword" class="input small" aria-label="Parole chiave predefinite">
            <option value="">Parole chiave predefinite</option>
            <option v-for="k in keywords" :key="k" :value="k">{{ k }}</option>
          </select>

          <input
            v-model="q"
            type="text"
            class="input small"
            placeholder="Oppure cerca parola..."
            aria-label="Ricerca testo libero"
          />
        </div>

        <select v-model="dateRange" class="input small" aria-label="Intervallo date">
          <option value="">Tutte le date</option>
          <option value="oggi">Oggi</option>
          <option value="7giorni">Ultimi 7 giorni</option>
          <option value="30giorni">Ultimi 30 giorni</option>
        </select>

        <select 
          v-model="categoryFilter" 
          @change="onCategoryChange" 
          class="input small" 
          aria-label="Filtro per categoria"
        >
          <option value="">Tutte le categorie</option>
          <option v-for="cat in categories" :key="cat.categoria_chat" :value="cat.categoria_chat">
            {{ cat.categoria_chat || 'Senza categoria' }} ({{ cat.totale }})
          </option>
        </select>

        <select v-model="chatFilter" class="input small" aria-label="Filtro per chat">
          <option value="">Tutte le chat {{ categoryFilter ? 'della categoria' : '' }}</option>
          <option v-for="c in filteredChats" :key="c.id_chat" :value="c.id_chat">
            {{ c.nome_chat_tradotto || c.nome_chat || 'Senza nome' }}
          </option>
        </select>

        <input v-model="userFilter" type="text" class="input small" placeholder="Utente o ID" aria-label="Filtro utente o ID" />

        <button class="btn" @click="doSearch" :disabled="loading">Cerca</button>
        <button class="btn btn-reset" type="button" @click="resetSearch" :disabled="loading">Reset</button>
      </div>
      <small v-if="mode==='ultimi'"></small>
      <small v-else-if="mode==='search'">Risultati ricerca con filtri attivi</small>
    </div>

    <div v-if="mode === 'search' && (selectedKeyword || q)" class="graph-banner">
      <div class="graph-banner-content">
        <div class="graph-icon">🕸️</div>
        <div class="graph-text">
          <strong>Visualizza rete di connessioni</strong>
          <p>Esplora come "{{ selectedKeyword || q }}" si collega ad altri termini e utenti</p>
        </div>
      </div>
      <button class="btn-graph" @click="visualizzaGrafo">
        <span class="graph-icon-btn">📊</span>
        Grafo
      </button>
    </div>

    <div v-if="loading" class="inline-loader" role="status" aria-live="polite">
      <div class="spinner" aria-hidden="true"></div>
      <span>Caricamento messaggi…</span>
    </div>

    <div v-if="!loading && messaggi.length === 0" class="empty-state">
      Nessun messaggio trovato.
    </div>

    <div
      v-for="m in messaggi"
      :key="m.id_messaggio"
      class="card msg rowlink fade-in"
      :class="{ 'msg-channel-official': isOfficialChannel(m) }"
    >
      <div class="msg-header">
        <div class="avatar-wrapper">
          <img
            v-if="avatarFor(m)"
            :src="avatarFor(m)"
            class="avatar clickable"
            @error="onAvatarError(m)"
            @click.stop="handleAuthorClick(m)"
          >
          <div 
            v-else 
            class="avatar avatar-fallback clickable" 
            :class="{ 'avatar-channel': isOfficialChannel(m) }"
            @click.stop="handleAuthorClick(m)"
          >
            {{ getAvatarContent(m) }}
          </div>
        </div>
        

        <div class="meta">
          <div class="author-line">
            <span class="author-name" @click.stop="handleAuthorClick(m)">
              {{ nameFor(m) }}
            </span>
            <span 
              v-if="usernameFor(m)" 
              class="author-handle" 
              @click.stop="handleAuthorClick(m)"
            >
              {{ usernameFor(m) }}
            </span>
          </div>

          <div class="info-line">
            <span class="light">{{ formatDate(m.data_invio || m.data) }}</span>
            
            <a 
              href="#" 
              class="tg-link"
              :class="{ 'tg-private': !isPublicChat(m) }"
              @click.stop.prevent="gestisciClickTelegram(m)"
              :title="isPublicChat(m) ? 'Apri su Telegram' : 'Gruppo Privato: Clicca per info su come accedere'"
            >
              <span v-if="isPublicChat(m)">✈️ Apri</span>
              <span v-else>🔒 Mostra in App</span>
            </a>

            <span class="pill pill-blue" v-if="m.provenienza && (m.nome || m.username)">
              #{{ m.provenienza_tradotta || m.provenienza }}
            </span>
            <span class="pill pill-gray" v-if="m.categoria_chat">
              {{ m.categoria_chat }}
            </span>
          </div>
        </div>
      </div>

      <span v-if="m.tipo_evento" class="pill pill-orange">
        {{ eventLabel(m.tipo_evento) }}
      </span>

      <div v-if="m.testo && m.testo !== '📎 Allegato'">
        <div v-if="m.reply_to_id" class="reply-preview">
          <div class="reply-line">
            <span class="muted">Risponde a</span>
            <router-link :to="`/utenti/${m.reply_to_id}`" class="reply-user">
              {{ m.reply_to_nome || ('@' + m.reply_to_username) || 'Utente sconosciuto' }}
            </router-link>
          </div>
          <div v-if="m.reply_to_testo" class="reply-quote">
            <span>{{ m.reply_to_testo }}</span>
          </div>
        </div>

        <p class="msg-text" v-html="m.testo"></p>

        <button
          v-if="!m.testo_tradotto && !m.translating"
          class="btn-translate"
          @click.stop="traduci(m)"
        >
          Traduci in italiano
        </button>

        <button
          v-else-if="m.testo_tradotto"
          class="btn-translate"
          @click.stop="m.testo_tradotto = ''"
        >
          Nascondi traduzione
        </button>

        <span v-if="m.translating" class="muted">Traduzione in corso...</span>
        <p v-if="m.translation_error" class="translation-error">{{ m.translation_error }}</p>
        <p v-if="m.testo_tradotto" class="tradotto">🇮🇹 {{ m.testo_tradotto }}</p>
      </div>

      <span v-else-if="m.testo === '📎 Allegato'" class="pill pill-gray">{{ m.testo }}</span>

      <div v-if="m.file_url" class="media">
        <a :href="m.file_url" target="_blank" rel="noopener">
          Apri allegato ({{ m.media_type || 'file' }})
        </a>
      </div>
    </div>

    <div class="pager soft-sticky">
      <button class="btn" :disabled="page<=1 || loading" @click="changePage(-1)">← Indietro</button>
      <button class="btn" :disabled="!hasMore || loading" @click="changePage(1)">Avanti →</button>
    </div>

    <div v-if="errorMsg" class="toast">
      {{ errorMsg }}
    </div>
  </div>
</template>

<script>
import { franc } from "franc-min";

export default {
  name: "Messaggi",
  data() {
    return {
      messaggi: [],
      page: 1,
      limit: 25,
      hasMore: false,
      loading: false,
      q: "",
      qShown: "",
      mode: "ultimi",
      chatInfo: {},
      userInfo: {},
      isGroupActive: false,
      errorMsg: "",
      showAdminDropdown: false,

      chats: [],
      categories: [],
      chatFilter: "",
      categoryFilter: "",
      userFilter: "",
      selectedKeyword: "",
      dateRange: "",

      keywords: ["ozempic", "semaglutide"],

      // --- STATO IMPORTAZIONE ---
      isImporting: false,
      importStatusMsg: "",
      importTarget: null,
      pollingInterval: null,
      pollingErrors: 0,
    };
  },

  computed: {
    chatId() {
      return this.$route.params.chatId ? Number(this.$route.params.chatId) : null;
    },
    userId() {
      return this.$route.params.userId ? Number(this.$route.params.userId) : null;
    },
    filteredChats() {
      if (!this.categoryFilter) return this.chats;
      return this.chats.filter(c => c.categoria_chat === this.categoryFilter);
    }
  },

  watch: {
    "$route.params.chatId": { 
      immediate: true, 
      handler() { 
        this.page = 1; 
        this.stopPolling();
        this.isImporting = false; 
        this.importStatusMsg = ""; 
        this.pollingErrors = 0;
        this.load(); 
      } 
    },
    "$route.params.userId": { 
      immediate: true, 
      handler() { 
        this.page = 1; 
        this.load(); 
      } 
    }
  },

  mounted() {
    if (!this.chatId && !this.userId) this.load();
    this.loadChats();
    this.loadCategories();
  },

  beforeUnmount() {
    this.stopPolling();
  },

  methods: {
    apiBase() {
      return "http://127.0.0.1:5000";
    },

    // ============================================
    // METODI IMPORTAZIONE
    // ============================================

    getImportTarget() {
      // Priorità: username > nome_chat > id
      if (this.chatInfo?.username) return this.chatInfo.username;
      if (this.chatInfo?.nome_chat) return this.chatInfo.nome_chat;
      if (this.chatId) return String(this.chatId);
      return null;
    },

    async checkInitialImportStatus() {
      const target = this.getImportTarget();
      if (!target) return;

      try {
        const res = await fetch(`${this.apiBase()}/api/import_status/${encodeURIComponent(target)}`);
        if (!res.ok) return;
        
        const json = await res.json();
        
        if (json.status === 'running') {
          this.isImporting = true;
          this.importTarget = target;
          this.importStatusMsg = json.progress || "Scansione in corso...";
          this.startPolling(target);
        }
      } catch (e) {
        console.debug("Nessuna scansione attiva per:", target);
      }
    },

    async lanciaScansione(mode = 'incrementale') {
      const chatName = this.chatInfo.nome_chat_tradotto || this.chatInfo.nome_chat || 'questa chat';
      const target = this.getImportTarget();

      if (!target) {
        this.errorMsg = "Impossibile determinare il target della chat.";
        return;
      }

      if (this.isImporting) return;
      
      if (!confirm(`Avviare scansione '${mode}' per "${chatName}"?`)) return;

      this.isImporting = true;
      this.importTarget = target;
      this.importStatusMsg = "Avvio connessione...";
      this.errorMsg = "";
      this.pollingErrors = 0;

      try {
        const res = await fetch(`${this.apiBase()}/api/importa_chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            target: target, 
            mode: mode,
            chat_id: this.chatId
          })
        });

        if (res.ok) {
          this.startPolling(target);
        } else {
          const errJson = await res.json().catch(() => ({ message: 'Errore API.' }));
          this.isImporting = false;
          this.importStatusMsg = `❌ Errore: ${errJson.message || 'Avvio fallito'}`;
        }
      } catch (e) {
        console.error("Errore avvio importazione:", e);
        this.isImporting = false;
        this.importStatusMsg = "❌ Errore di rete.";
      }
    },

    startPolling(target) {
      this.stopPolling();
      
      const MAX_ERRORS = 3;
      
      const poll = async () => {
        try {
          const res = await fetch(`${this.apiBase()}/api/import_status/${encodeURIComponent(target)}`);
          
          if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
          }
          
          const json = await res.json();
          this.pollingErrors = 0; // Reset errori su successo
          
          if (json.progress) {
            this.importStatusMsg = json.progress;
          }

          if (json.status === 'done') {
            this.stopPolling();
            this.isImporting = false;
            this.importStatusMsg = json.progress || "✅ Completato!";
            
            // Ricarica i dati
            setTimeout(() => {
              this.load();
              this.loadChats();
            }, 1500);

          } else if (json.status === 'error') {
            this.stopPolling();
            this.isImporting = false;
            this.importStatusMsg = `❌ ${json.progress || 'Errore durante la scansione.'}`;
            
          } else if (json.status === 'idle' || !json.status) {
            // Nessuna scansione attiva - potrebbe essere stata completata
            this.pollingErrors++;
            if (this.pollingErrors >= MAX_ERRORS) {
              this.stopPolling();
              this.isImporting = false;
              this.importStatusMsg = "ℹ️ Scansione non trovata o già completata.";
            }
          }
          
        } catch (e) {
          console.warn("Errore polling:", e);
          this.pollingErrors++;
          
          if (this.pollingErrors >= MAX_ERRORS) {
            this.stopPolling();
            this.isImporting = false;
            this.importStatusMsg = "⚠️ Connessione persa. Riprova.";
          }
        }
      };

      // Prima chiamata immediata
      poll();
      
      // Poi ogni 2.5 secondi
      this.pollingInterval = setInterval(poll, 2500);
    },

    stopPolling() {
      if (this.pollingInterval) {
        clearInterval(this.pollingInterval);
        this.pollingInterval = null;
      }
    },

    // ============================================
    // METODI ESISTENTI
    // ============================================

    tornaAllaVistaIniziale() {
      this.resetSearch();
      this.chatInfo = {};
      this.userInfo = {};
      this.mode = "ultimi";
      this.$router.push("/messaggi");
    },

    getAvatarContent(m) {
      if (this.isOfficialChannel(m)) return '📢';
      if (this.isChannel(m)) return '📡';
      return this.getInitial(m);
    },

    async loadChats() {
      try {
        const res = await fetch(`${this.apiBase()}/api/chats?limit=200`);
        const json = await res.json();
        this.chats = json.data || [];
      } catch (e) {
        console.error("Errore caricamento chat:", e);
      }
    },

    async loadCategories() {
      try {
        const res = await fetch(`${this.apiBase()}/api/chat_per_categoria`);
        const json = await res.json();
        this.categories = json.data || [];
      } catch (e) {
        console.error("Errore caricamento categorie:", e);
      }
    },

    onCategoryChange() {
      if (this.chatFilter) {
        const selectedChatObj = this.chats.find(c => c.id_chat == this.chatFilter);
        if (selectedChatObj && selectedChatObj.categoria_chat !== this.categoryFilter) {
           this.chatFilter = "";
        }
      }
    },

    async load() {
      this.loading = true;
      this.errorMsg = "";
      try {
        const offset = (this.page - 1) * this.limit;
        const base = this.apiBase();
        let json;

        if (this.userId) {
          this.mode = "user";
          const chatId = this.$route.query.chat_id || "";
          const url = `${base}/api/messaggi_utente/${this.userId}?limit=${this.limit}&offset=${offset}${chatId ? `&chat_id=${chatId}` : ""}`;
          const res = await fetch(url);
          json = await res.json();
          this.userInfo = json.user || {};
          this.messaggi = json.data || [];
        }
        else if (this.chatId) {
          this.mode = "chat";
          try {
            const infoRes = await fetch(`${base}/api/chat_info/${this.chatId}`);
            const infoJson = await infoRes.json();
            this.chatInfo = infoJson?.data || {};

            if (this.chatInfo.ultima_scansione) {
              const lastScan = new Date(this.chatInfo.ultima_scansione);
              const now = new Date();
              const diffDays = (now - lastScan) / (1000 * 60 * 60 * 24);
              this.isGroupActive = diffDays <= 30;
            }
          } catch {
            this.chatInfo = {};
          }

          // Controlla se c'è una scansione attiva DOPO aver caricato chatInfo
          this.checkInitialImportStatus();

          const res = await fetch(`${base}/api/messaggi/${this.chatId}?limit=${this.limit}&offset=${offset}`);
          json = await res.json();
          this.messaggi = json.data || [];
        }
        else if (this.mode === "search") {
          const params = new URLSearchParams({
            limit: this.limit,
            offset,
          });

          if (this.selectedKeyword) params.append("keywords", this.selectedKeyword);
          if (this.q) params.append("q", this.q);
          if (this.chatFilter) params.append("chat_id", this.chatFilter);
          if (this.userFilter) params.append("id_autore", this.userFilter);
          if (this.categoryFilter) params.append("categoria", this.categoryFilter);

          if (this.dateRange) {
            const now = new Date();
            let start = null;

            if (this.dateRange === "oggi") {
              start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            } else if (this.dateRange === "7giorni") {
              start = new Date(now); start.setDate(now.getDate() - 7);
            } else if (this.dateRange === "30giorni") {
              start = new Date(now); start.setDate(now.getDate() - 30);
            }

            if (start) {
              params.append("data_inizio", start.toISOString());
              params.append("data_fine", now.toISOString());
            }
          }

          const res = await fetch(`${base}/api/cerca_messaggi?${params.toString()}`);
          json = await res.json();
          this.messaggi = json.data || [];
        }
        else {
          this.mode = "ultimi";
          const res = await fetch(`${base}/api/ultimi_messaggi?limit=${this.limit}&offset=${offset}`);
          const data = await res.json();
          this.messaggi = data?.data || data || [];
          json = { has_more: false };
        }

        this.hasMore = json?.has_more !== undefined ? !!json.has_more : this.messaggi.length === this.limit;

        for (const m of this.messaggi) {
          if (m.testo) {
            const lang = franc(m.testo || "");
            m.lang = lang || "und";
          }
        }

      } catch (e) {
        console.error(e);
        this.errorMsg = "Si è verificato un errore nel caricamento. Riprova.";
        this.messaggi = [];
        this.hasMore = false;
      } finally {
        this.loading = false;
      }
    },

    async doSearch() {
      this.page = 1;
      this.mode = "search";
      await this.load();
    },

    resetSearch() {
      this.selectedKeyword = "";
      this.chatFilter = "";
      this.categoryFilter = "";
      this.userFilter = "";
      this.dateRange = "";
      this.q = "";
      this.qShown = "";
      this.page = 1;
      this.mode = "ultimi";
      this.load();
    },

    visualizzaGrafo() {
      const keyword = this.selectedKeyword || this.q;
      const chat = this.chatFilter || "";

      const params = new URLSearchParams();

      if (keyword) params.append("term", keyword);
      if (chat) params.append("chat", chat);

      if (this.dateRange) {
        const now = new Date();
        let start = null;

        if (this.dateRange === "oggi") {
          start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        } else if (this.dateRange === "7giorni") {
          start = new Date(now); start.setDate(now.getDate() - 7);
        } else if (this.dateRange === "30giorni") {
          start = new Date(now); start.setDate(now.getDate() - 30);
        }

        if (start) {
          params.append("start", start.toISOString());
          params.append("end", now.toISOString());
        }
      }

      this.$router.push({
        name: "GrafoFiltrato",
        query: Object.fromEntries(params)
      });
    },

    async traduci(m) {
      try {
        m.translating = true;
        m.translation_error = "";
        const res = await fetch(`${this.apiBase()}/api/traduci`, {
          method: "POST",
          body: JSON.stringify({ q: m.testo, source: m.lang || franc(m.testo || "") }),
          headers: { "Content-Type": "application/json" },
        });
        const json = await res.json();
        if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
        if (json.translatedText) m.testo_tradotto = json.translatedText;
      } catch (e) {
        console.error("Errore traduzione:", e);
        m.translation_error = e.message || "Traduzione non disponibile";
      } finally {
        m.translating = false;
      }
    },

    eventLabel(tipo) {
      const map = {
        "MessageActionChatAddUser": "➕ Utente aggiunto",
        "MessageActionChatJoinedByLink": "🔗 Entrato via link",
        "MessageActionChatDeleteUser": "🚪 Utente rimosso",
        "MessageActionChatCreate": "📌 Creazione chat",
        "MessageActionChannelCreate": "📢 Creazione canale",
        "MessageActionPinMessage": "📍 Messaggio fissato",
        "MessageActionChatEditTitle": "✏️ Titolo cambiato",
        "MessageActionChatEditPhoto": "🖼️ Foto cambiata",
      };
      return map[tipo] || `⚡ Evento: ${tipo}`;
    },

    nameFor(m) {
      if (this.userId && this.userInfo) {
        return this.userInfo.username ? `@${this.userInfo.username}` : this.userInfo.nome || "";
      }
      
      if (m.id_autore && m.id_chat && m.id_autore === m.id_chat && m.id_autore < 0) {
        const nomeCanale = m.provenienza_tradotta || m.provenienza || `Canale ${Math.abs(m.id_autore)}`;
        return `📢 ${nomeCanale}`;
      }
      
      if (m.nome && m.nome.trim() && !m.nome.startsWith("Canale Esterno")) {
        return m.nome;
      }
      if (m.username) return `@${m.username}`;
      
      if (m.id_autore && m.id_autore < 0) {
        if (m.provenienza_tradotta) return `📡 ${m.provenienza_tradotta}`;
        if (m.provenienza) return `📡 ${m.provenienza}`;
        return `📡 Canale ${Math.abs(m.id_autore)}`;
      }
      
      if (m.provenienza_tradotta || m.provenienza) {
        return m.provenienza_tradotta || m.provenienza;
      }
      
      return "Utente Sconosciuto";
    },

    isChannel(m) {
      return (m.id_autore && m.id_chat && m.id_autore === m.id_chat && m.id_autore < 0) ||
              (m.id_autore && m.id_autore < 0 && !m.nome && !m.username);
    },

    isOfficialChannel(m) {
      return m.id_autore && m.id_chat && m.id_autore === m.id_chat && m.id_autore < 0;
    },

    getInitial(m) {
      if (m.nome) return m.nome[0].toUpperCase();
      if (m.username) return m.username[0].toUpperCase();
      return "?";
    },

    isPublicChat(m) {
      return !!(m.chat_username || this.chatInfo?.username);
    },

    getTelegramLink(m) {
      const username = m.chat_username || this.chatInfo?.username;
      if (username) {
        return `https://t.me/${username}/${m.id_messaggio}`;
      }
      let chatId = (m.id_chat || this.chatId || "").toString();
      if (chatId.startsWith("-100")) chatId = chatId.substring(4); 
      else if (chatId.startsWith("-")) chatId = chatId.substring(1);
      return `https://t.me/c/${chatId}/${m.id_messaggio}`;
    },

    gestisciClickTelegram(m) {
      const link = this.getTelegramLink(m);
      const nomeChat = m.nome_chat || m.provenienza || m.nome_chat_tradotto || m.provenienza_tradotta || "questo gruppo";

      if (this.isPublicChat(m)) {
        window.open(link, '_blank');
        return;
      }

      const conferma = window.confirm(
        `🔒 GRUPPO PRIVATO: "${nomeChat}"\n\n` +
        `Questo messaggio è in una chat privata. Per vederlo su Telegram, devi essere già membro del gruppo.\n\n` +
        `• SEI GIÀ MEMBRO? Premi OK per aprire il messaggio.\n` +
        `• NON SEI MEMBRO? Premi Annulla, poi cerca "${nomeChat}" su Telegram per unirti.`
      );

      if (conferma) {
        window.open(link, '_blank');
      }
    },

    usernameFor(m) {
      if (this.userId && this.userInfo) {
        return this.userInfo.username ? `@${this.userInfo.username}` : "";
      }
      
      if (m.id_autore && m.id_chat && m.id_autore === m.id_chat && m.id_autore < 0) {
        return "Canale Ufficiale";
      }
      
      if (m.username) return `@${m.username}`;
      
      if (this.isChannel(m)) return "Canale";
      
      return "";
    },

    handleAuthorClick(m) {
      if (m.id_autore && m.id_autore < 0 && m.id_chat) {
        this.$router.push(`/messaggi/${m.id_chat}`);
      }
      else if ((m.nome || m.username) && m.id_autore && m.id_autore > 0) {
        this.$router.push(`/utenti/${m.id_autore}`);
      } 
      else if (m.id_chat) {
        this.$router.push(`/messaggi/${m.id_chat}`);
      }
    },

    avatarFor(m) {
      return this.userId && this.userInfo
        ? (this.userInfo.avatar_url || "")
        : (m.avatar_url || "");
    },

    onAvatarError(m) {
      if (this.userId && this.userInfo) this.userInfo.avatar_url = "";
      else m.avatar_url = "";
    },

    changePage(delta) {
      if (this.loading) return;
      this.page += delta;
      this.load();
      window.scrollTo({ top: 0, behavior: "smooth" });
    },

    openUser(id) {
      if (id) this.$router.push(`/utenti/${id}`);
    },

    toggleAdminDropdown() {
      this.showAdminDropdown = !this.showAdminDropdown;
    },

    formatDate(d) {
      if (!d) return "—";
      const needsZ = typeof d === "string" &&
        /^\d{4}-\d{2}-\d{2}T/.test(d) &&
        !/[Z\+\-]\d{2}:?\d{2}$/.test(d);
      const dt = new Date(needsZ ? d + "Z" : d);
      return isNaN(dt.getTime()) ? d : dt.toLocaleString("it-IT");
    }
  }
};
</script>
<style scoped>
/* Anti-FoUC */
[v-cloak] { 
  display: none; 
}

.messages-header .page-title {
  margin: 0 0 0.35rem;
  color: #0f172a;
  font-size: clamp(2rem, 3vw, 2.65rem);
  line-height: 1.08;
  letter-spacing: -0.04em;
}

.messages-header .btn-back { flex: 0 0 auto; margin-top: 0.35rem; }

.user-activity-banner {
  margin-bottom: 1rem;
  padding: 0.85rem 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 13px;
  box-shadow: 0 1px 2px rgba(15,23,42,0.03);
}

.user-activity-banner strong { color: #334155; font-size: 0.88rem; }

/* --- FILTRI E INPUT --- */
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.8rem;
  justify-content: flex-start;
}

.input.small,
select.input.small {
  appearance: none;
  -webkit-appearance: none; 
  -moz-appearance: none;
  background-color: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.6rem 2.5rem 0.6rem 1rem;
  font-size: 0.9rem;
  color: #334155;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2364748b'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0.7rem center;
  background-size: 1rem;
  min-width: 180px;
  max-width: 100%;
}

.input.small:hover,
select.input.small:hover {
  border-color: #cbd5e1;
  background-color: #f8fafc;
}

.input.small:focus,
select.input.small:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
  background-color: #fff;
}

input.input.small {
  background-image: none; 
  padding-right: 1rem;
  cursor: text;
}

.keyword-search {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-grow: 1;
}

.keyword-search select {
  min-width: 140px;
  background-color: #f1f5f9;
  border-color: #cbd5e1;
  font-weight: 500;
}

.keyword-search input {
  flex-grow: 1;
}

/* --- BOTTONI --- */
.btn { 
  padding: .6rem 1.2rem; 
  border-radius: 8px; 
  border: 1px solid transparent; 
  background: #1e4fd1;
  color: #fff; 
  cursor: pointer; 
  font-size: 0.9rem; 
  font-weight: 600; 
  transition: all .2s ease; 
  box-shadow: 0 2px 4px rgba(30, 79, 209, 0.2);
}

.btn:hover { 
  background: #153eaa; 
  transform: translateY(-1px);
  box-shadow: 0 4px 6px rgba(30, 79, 209, 0.3);
}

.btn:disabled { 
  opacity: .6; 
  cursor: not-allowed; 
  transform: none;
}

.btn-reset {
  background: #fff;
  color: #475569;
  border: 1px solid #cbd5e1;
  box-shadow: none;
}

.btn-reset:hover {
  background: #f1f5f9;
  color: #1e293b;
  border-color: #94a3b8;
  transform: translateY(-1px);
}

.search-bar {
  background: #fff;
  border-radius: 15px;
  padding: 0.9rem;
  margin-bottom: 1rem;
  box-shadow: 0 4px 18px rgba(15,23,42,0.045);
  border: 1px solid #dfe6ef;
}

@media (max-width: 1024px) {
  .filters {
    flex-direction: column;
    align-items: stretch;
  }
  .keyword-search {
    flex-direction: column;
    width: 100%;
  }
  .input.small, select.input.small, .btn {
    width: 100%;
  }
}

/* --- BANNER GRAFO --- */
.graph-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
  border: 2px solid #c7d2fe;
  border-radius: 16px;
  padding: 1.2rem 1.5rem;
  margin-bottom: 1.5rem;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.1);
  animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

.graph-banner-content { 
  display: flex; 
  align-items: center; 
  gap: 1rem; 
  flex: 1; 
}

.graph-icon { 
  font-size: 2rem; 
  line-height: 1; 
}

.graph-text { 
  display: flex; 
  flex-direction: column; 
  gap: 0.2rem; 
}

.graph-text strong { 
  color: #1e3a8a; 
  font-size: 1.05rem; 
  font-weight: 600; 
}

.graph-text p { 
  margin: 0; 
  color: #475569; 
  font-size: 0.9rem; 
}

.btn-graph {
  display: flex; 
  align-items: center; 
  gap: 0.5rem; 
  padding: 0.7rem 1.4rem;
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  color: white; 
  border: none; 
  border-radius: 12px;
  font-size: 0.95rem; 
  font-weight: 600; 
  cursor: pointer;
  transition: all 0.3s ease; 
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
  white-space: nowrap;
}

.btn-graph:hover {
  background: linear-gradient(135deg, #4f46e5 0%, #4338ca 100%);
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4);
}

.graph-icon-btn { 
  font-size: 1.2rem; 
  line-height: 1; 
}

/* --- HEADER INFO CHAT --- */
.chat-info-header { 
  display: flex; 
  align-items: flex-start; 
  gap: 1rem; 
  position: relative;
}

.avatar-xl { 
  width: 64px; 
  height: 64px; 
  border-radius: 50%; 
  object-fit: cover; 
  border: 2px solid #e5eaf0; 
  box-shadow: 0 3px 8px rgba(0,0,0,0.08);
  flex-shrink: 0;
}

.avatar-fallback { 
  background: linear-gradient(135deg,#94a3b8,#64748b); 
  display: flex; 
  align-items: center; 
  justify-content: center; 
  font-size: 1rem; 
  color: #fff; 
  border-radius: 50%; 
  font-weight: 600;
  box-shadow: inset 0 1px 2px rgba(255,255,255,0.2);
}

.meta {
  flex: 1;
  min-width: 0;
}

/* CONTROLLI SCANNER */
.scan-controls {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1rem;
    padding: 0.8rem 0; 
    border-bottom: 1px dashed #e5eaf0;
}

.btn-scan {
    /* Verde per scansione */
    background: linear-gradient(135deg, #16a34a, #166534); 
    font-size: 0.95rem;
    padding: 0.8rem 1.5rem;
    color: white;
    border: none;
    border-radius: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.25s ease;
}

.btn-scan:hover:not(:disabled) {
    background: linear-gradient(135deg, #15803d, #145214);
    box-shadow: 0 4px 8px rgba(22, 163, 74, 0.3);
    transform: translateY(-1px);
}

.btn-scan:disabled {
    opacity: 0.7;
    cursor: not-allowed;
    transform: none;
}

.import-status-bar {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    background: #f0fdf4; /* Light green background */
    border: 1px solid #d1fae5;
    padding: 0.6rem 1rem;
    border-radius: 8px;
    font-size: 0.9rem;
    font-weight: 500;
    color: #065f46;
}
.import-status-bar .status-text {
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-icon {
    font-size: 1.1rem;
    line-height: 1;
    flex-shrink: 0;
}

/* Animazione rotazione */
.icon-spin {
    animation: spin 1s linear infinite;
    color: #3b82f6; 
}
.icon-done {
    color: #16a34a;
}
@keyframes spin { 
  100% { transform: rotate(360deg); } 
}


/* --- MESSAGGI --- */
.msg { 
  display: flex; 
  flex-direction: column; 
  gap: .6rem; 
  padding: 1.1rem 1.3rem; 
  border: 1px solid #e5eaf0; 
  border-radius: 15px;
  background: #fff; 
  transition: all .25s ease; 
  margin-bottom: .9rem; 
  box-shadow: 0 3px 12px rgba(15,23,42,0.04);
}

.msg:hover {
  background: #f9fbff; 
  border-color: #cbd5e1; 
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(15,23,42,0.065);
}

/* 📢 Messaggi del canale ufficiale */
.msg-channel-official {
  background: linear-gradient(135deg, #fff7ed 0%, #fffbeb 100%);
  border-left: 4px solid #f59e0b;
  border-color: #fed7aa;
}

.msg-channel-official:hover {
  background: linear-gradient(135deg, #fff7ed 0%, #fef3c7 100%);
  border-color: #fbbf24;
}

.fade-in { 
  animation: fadeIn .25s ease-out; 
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(2px); }
  to { opacity: 1; transform: translateY(0); }
}

.msg-header { 
  display: flex; 
  align-items: center; 
  gap: .8rem; 
}

.avatar { 
  width: 44px; 
  height: 44px; 
  border-radius: 50%; 
  object-fit: cover; 
  border: 2px solid #e5eaf0; 
}

.avatar.clickable { 
  cursor: pointer; 
  transition: transform 0.2s ease; 
}

.avatar.clickable:hover { 
  transform: scale(1.05); 
  border-color: #1e4fd1; 
}

.avatar-channel { 
  background: linear-gradient(135deg, #f59e0b, #d97706) !important; 
  font-size: 1.2rem; 
}

.author-line { 
  display: flex; 
  align-items: baseline; 
  gap: 0.5rem; 
  flex-wrap: wrap; 
}

.author-name { 
  font-weight: 700; 
  font-size: 1rem; 
  color: #1e4fd1; 
  cursor: pointer; 
  transition: color 0.2s ease; 
}

.author-name:hover { 
  color: #153eaa; 
  text-decoration: underline; 
}

.author-handle { 
  font-size: 0.85rem; 
  color: #64748b; 
  font-weight: 400; 
  cursor: pointer; 
}

.author-handle:hover { 
  color: #1e4fd1; 
}

.info-line { 
  display: flex; 
  align-items: center; 
  gap: 0.6rem; 
  flex-wrap: wrap; 
}

.light { 
  font-size: .83rem; 
  color: #64748b; 
}

.msg-text { 
  white-space: pre-wrap; 
  font-size: .96rem; 
  line-height: 1.55; 
  color: #1f2937; 
}

.reply-info { 
  font-size: 0.85rem; 
  color: #475569; 
  margin-top: 0.25rem; 
  padding-left: 0.7rem; 
  border-left: 3px solid #d1d9e6; 
}

.reply-user { 
  font-weight: 600; 
  color: #1e4fd1; 
  cursor: pointer; 
  text-decoration: underline; 
  transition: color 0.2s ease; 
}

.reply-user:hover { 
  color: #153eaa; 
  text-decoration: none; 
}

.media a { 
  display: inline-block; 
  margin-top: .35rem; 
  font-size: .9rem; 
  color: #1e4fd1; 
  font-weight: 500; 
  text-decoration: underline; 
  transition: color 0.2s ease; 
}

.media a:hover { 
  color: #153eaa; 
  text-decoration: none; 
}

/* --- PILLS --- */
.pill { 
  padding: .25rem .65rem; 
  border-radius: 999px; 
  font-size: .72rem; 
  font-weight: 600; 
  letter-spacing: .25px; 
  line-height: 1.3; 
}

.pill-blue { 
  background: #eaf2ff; 
  color: #1e40af; 
  border: 1px solid #c7d2fe; 
}

.pill-green { 
  background: #ecfdf5; 
  color: #047857; 
  border: 1px solid #a7f3d0; 
}

.pill-gray { 
  background: #f8fafc; 
  color: #475569; 
  border: 1px solid #e2e8f0; 
}

.pill-orange { 
  background: #fff7ed; 
  color: #c2410c; 
  border: 1px solid #fdba74; 
}

.title-line { 
  display: flex; 
  align-items: center; 
  gap: .5rem; 
}

.sub-line { 
  color: #475569; 
  display: flex; 
  align-items: center; 
  gap: .25rem; 
  flex-wrap: wrap; 
}

.sub-line.small { 
  font-size: .9rem; 
}

.muted { 
  color: #94a3b8; 
}

.chat-name { 
  margin: 0; 
}

/* --- STATUS CHAT --- */
.chat-status { 
  margin-top: 0.4rem; 
  font-size: 0.88rem; 
  font-weight: 500; 
  display: flex; 
  align-items: center; 
  gap: 0.4rem; 
}

.status-active { 
  color: #166534; 
  background: #f0fdf4; 
  border: 1px solid #bbf7d0; 
  padding: 0.35rem 0.7rem; 
  border-radius: 8px; 
  display: flex; 
  align-items: center; 
  gap: 0.4rem; 
}

.status-inactive { 
  color: #7c2d12; 
  background: #fff7ed; 
  border: 1px solid #fed7aa; 
  padding: 0.35rem 0.7rem; 
  border-radius: 8px; 
  display: flex; 
  align-items: center; 
  gap: 0.4rem; 
}

.dot { 
  width: 9px; 
  height: 9px; 
  border-radius: 50%; 
  background: #22c55e; 
}

.dot.orange { 
  background: #f59e0b; 
}

/* --- TRADUZIONE --- */
.tradotto { 
  margin-top: .4rem; 
  font-size: .9rem; 
  font-style: italic; 
  color: #1e3a8a; 
  background: #f0f6ff; 
  padding: .4rem .7rem; 
  border-left: 3px solid #3b82f6; 
  border-radius: 6px; 
}

.btn-translate { 
  margin-top: .4rem; 
  padding: .4rem .85rem; 
  border: 1px solid #d1d9e6; 
  border-radius: 8px; 
  cursor: pointer; 
  font-size: 0.8rem; 
  background: linear-gradient(180deg,#ffffff,#f8fafc); 
  transition: all .25s ease; 
}

.btn-translate:hover { 
  background: #3b82f6; 
  color: #fff; 
  border-color: #3b82f6; 
  box-shadow: 0 3px 6px rgba(59,130,246,0.3); 
}

/* --- PAGINAZIONE --- */
.pager { 
  display: flex; 
  align-items: center; 
  gap: .8rem; 
  margin-top: 1rem; 
  justify-content: center; 
}

.soft-sticky { 
  position: sticky; 
  bottom: 0; 
  background: linear-gradient(180deg, rgba(255,255,255,0), #fff 40%); 
  padding-bottom: .4rem; 
}

/* --- TOOLBAR --- */
.toolbar { 
  display: flex; 
  justify-content: flex-end; 
  margin-bottom: 0.8rem; 
}

.btn-back { 
  display: flex; 
  align-items: center; 
  gap: 0.4rem; 
  padding: 0.55rem 1rem; 
  border-radius: 12px; 
  border: 1px solid #cbd5e1; 
  background: linear-gradient(180deg, #ffffff, #f8fafc); 
  color: #1e3a8a; 
  font-size: 0.9rem; 
  font-weight: 500; 
  cursor: pointer; 
  transition: all 0.25s ease; 
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05); 
}

.btn-back:hover { 
  background: #1e4fd1; 
  color: #fff; 
  border-color: #1e4fd1; 
  box-shadow: 0 3px 8px rgba(30, 79, 209, 0.25); 
  transform: translateY(-1px); 
}

.btn-back:active { 
  transform: translateY(0); 
}

.btn-back .icon { 
  font-size: 1rem; 
  line-height: 1; 
  transition: transform 0.2s ease; 
}

.btn-back:hover .icon { 
  transform: translateX(-2px); 
}

/* --- UTILITY --- */
.rowlink { 
  cursor: pointer; 
}

.inline-loader { 
  display: flex; 
  align-items: center; 
  gap: .6rem; 
  padding: .75rem 1rem; 
  border: 1px solid #e5eaf0; 
  border-radius: 12px; 
  background: #f8fafc; 
  color: #334155; 
  margin: .5rem 0 1rem; 
}

.spinner { 
  width: 18px; 
  height: 18px; 
  border: 2px solid #c7d2fe; 
  border-top-color: #1e4fd1; 
  border-radius: 50%; 
  animation: spin .8s linear infinite; 
}

@keyframes spin { 
  to { transform: rotate(360deg); } 
}

.empty-state { 
  padding: 1.2rem 1rem; 
  border: 1px dashed #cbd5e1; 
  border-radius: 12px; 
  color: #64748b; 
  background: #f8fafc; 
  text-align: center; 
}

.toast { 
  position: fixed; 
  right: 1rem; 
  bottom: 1rem; 
  background: #fff1f2; 
  color: #7f1d1d; 
  border: 1px solid #fecdd3; 
  padding: .7rem 1rem; 
  border-radius: 10px; 
  box-shadow: 0 6px 16px rgba(0,0,0,0.08); 
  animation: slideUp .25s ease-out; 
}

@keyframes slideUp { 
  from { opacity: 0; transform: translateY(6px); } 
  to { opacity: 1; transform: translateY(0); } 
}

/* --- REPLY PREVIEW --- */
.reply-preview { 
  margin-top: 0.6rem; 
  padding: 0.6rem 0.8rem; 
  border-left: 3px solid #93c5fd; 
  background: #f1f5ff; 
  border-radius: 6px; 
  color: #1e3a8a; 
  font-size: 0.9rem; 
}

.reply-line { 
  display: flex; 
  align-items: center; 
  gap: 0.4rem; 
  margin-bottom: 0.2rem; 
}

.reply-quote { 
  font-style: italic; 
  color: #334155; 
  background: #fff; 
  border-radius: 5px; 
  padding: 0.3rem 0.6rem; 
  border: 1px solid #e2e8f0; 
  font-size: 0.85rem; 
  max-width: 90%; 
  white-space: nowrap; 
  overflow: hidden; 
  text-overflow: ellipsis; 
}

/* --- TELEGRAM LINK --- */
.tg-link { 
  display: inline-flex; 
  align-items: center; 
  gap: 0.3rem; 
  font-size: 0.75rem; 
  font-weight: 600; 
  color: #0088cc; 
  background-color: #e3f2fd; 
  padding: 0.2rem 0.5rem; 
  border-radius: 6px; 
  text-decoration: none; 
  transition: all 0.2s ease; 
  border: 1px solid transparent; 
}

.tg-link:hover { 
  background-color: #0088cc; 
  color: white; 
  border-color: #0077b5; 
  transform: translateY(-1px); 
  box-shadow: 0 2px 4px rgba(0, 136, 204, 0.2); 
}

.tg-link.tg-private { 
  color: #b45309; 
  background-color: #fffbeb; 
  border-color: #fcd34d; 
  cursor: help; 
}

.tg-link.tg-private:hover { 
  background-color: #f59e0b; 
  color: white; 
  border-color: #d97706; 
}

.tg-link:active { 
  transform: translateY(0); 
}

/* ==========================================
  ADMIN CARD CON DROPDOWN - NUOVI STILI
  ========================================== */
.chat-admins {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
  padding: 16px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.admin-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.admin-icon {
  font-size: 1.1rem;
  line-height: 1;
}

.admin-label {
  font-weight: 700;
  font-size: 0.95rem;
  color: #1e293b;
}

.admin-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 8px;
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: white;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 700;
  box-shadow: 0 2px 4px rgba(99, 102, 241, 0.2);
}

.admin-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.admin-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.admin-badge:hover {
  background: #1e4fd1;
  border-color: #1e4fd1;
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(30, 79, 209, 0.2);
}

.admin-badge:hover .admin-avatar {
  background: white;
  color: #1e4fd1;
}

.admin-badge:hover .admin-name {
  color: white;
}

.admin-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: white;
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: 700;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.admin-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: #334155;
  transition: color 0.2s ease;
}

.admin-dropdown {
  position: relative;
}

.admin-more-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 4px rgba(99, 102, 241, 0.2);
}

.admin-more-btn:hover {
  background: linear-gradient(135deg, #4f46e5, #4338ca);
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(99, 102, 241, 0.3);
}

.dropdown-arrow {
  font-size: 0.7rem;
  transition: transform 0.2s ease;
}

.admin-more-btn:hover .dropdown-arrow {
  transform: translateY(1px);
}

.admin-dropdown-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 200px;
  max-height: 300px;
  overflow-y: auto;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
  z-index: 100;
  animation: dropdownFadeIn 0.2s ease;
}

@keyframes dropdownFadeIn {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.admin-dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  border-bottom: 1px solid #f1f5f9;
}

.admin-dropdown-item:last-child {
  border-bottom: none;
}

.admin-dropdown-item:hover {
  background: #f8fafc;
}

.admin-dropdown-item:hover .admin-avatar {
  transform: scale(1.1);
}

.admin-dropdown-item .admin-name {
  font-size: 0.875rem;
}
</style>
