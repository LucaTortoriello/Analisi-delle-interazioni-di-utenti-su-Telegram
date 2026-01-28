<template>
  <div>
    <h1 class="page-title" v-if="!userId">Utenti</h1>
    <h1 class="page-title" v-else>Dettaglio Utente</h1>

    <div v-if="!userId">
      <div class="search-bar-group">
        <div class="input-with-btn">
          <input
            v-model="searchUser"
            class="input"
            type="text"
            placeholder="🔎 Nome, username o ID utente..."
            @keyup.enter="searchUsersUnified"
          />
          <button class="btn" @click="searchUsersUnified">Cerca</button>
        </div>

        <p v-if="searchError" class="error-msg">{{ searchError }}</p>

        <div class="input-with-btn">
          <input
            v-model="searchIdGlobal"
            class="input"
            type="number"
            placeholder="ID utente → chat"
          />
          <button class="btn" @click="findChatsByUserId">Cerca</button>
        </div>
      </div>

      <div v-if="searchedChats.length" class="card">
        <h3>Chat in cui potrebbe essere l'utente {{ searchIdGlobal }}</h3>
        <table class="table">
          <thead>
            <tr>
              <th>Nome</th>
              <th>Tipo</th>
              <th>Messaggi</th>
              <th>Prima</th>
              <th>Ultima</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in searchedChats" :key="c.id_chat">
              <td>
                <router-link :to="`/messaggi/${c.id_chat}`">
                  {{ c.nome_chat_tradotto || c.nome_chat }}
                </router-link>
              </td>
              <td>{{ c.tipo }}</td>
              <td>{{ c.messaggi_utente }}</td>
              <td>{{ formatDate(c.prima_interazione) }}</td>
              <td>{{ formatDate(c.ultima_interazione) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        v-else-if="searchPerformed && searchIdGlobal && !searchedChats.length"
        class="error-msg"
      >
        Utente non trovato
      </div>

      <div v-if="filteredUtenti.length" class="card">
        <h3>Elenco utenti</h3>
        <table class="table">
          <thead>
            <tr>
              <th>Foto profilo</th>
              <th>Nome</th>
              <th>ID</th>
              <th>Username</th>
              <th>Data importazione</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="u in filteredUtenti"
              :key="u.id"
              @click="openUser(u.id)"
              class="rowlink"
            >
              <td>
                <img v-if="u.avatar_url" :src="u.avatar_url" class="avatar" />
                <div v-else class="avatar avatar-fallback">?</div>
              </td>
              <td>{{ u.nome || "—" }}</td>
              <td>
                <span class="pill pill-gray" style="font-size: 0.75rem;">{{ u.id }}</span>
              </td>
              <td>{{ u.username ? '@' + u.username : "Sconosciuto" }}</td>
              <td>{{ formatDate(u.data_importazione) }}</td>
            </tr>
          </tbody>
        </table>

        <div class="pager">
          <button class="btn" :disabled="page<=1" @click="changePage(-1)">
            ← Indietro
          </button>
          <button class="btn" :disabled="!hasMore || loading" @click="changePage(1)">
            Avanti →
          </button>
        </div>
      </div>
      <div
        v-else-if="searchPerformed && searchUser && !filteredUtenti.length"
        class="error-msg"
      >
        Utente non trovato
      </div>
    </div>

    <!-- ==================== DETTAGLIO UTENTE ==================== -->
    <div v-else class="user-detail">
      <div class="card user-card">
        <div class="header">
          <div class="avatar-wrapper">
            <img
              v-if="user.avatar_url"
              :src="user.avatar_url"
              class="avatar-xl"
              @error="user.avatar_url = ''"
            />
            <div v-else class="avatar-xl avatar-fallback">?</div>
          </div>
          <div>
            <h2 class="username">{{ user.nome || user.username || "Utente" }}</h2>
            <div class="meta">
              <span v-if="user.username" class="pill">@{{ user.username }}</span>
              <span v-if="user.data_importazione" class="pill pill-gray">
                Importato: {{ formatDate(user.data_importazione) }}
              </span>
              <span v-if="user.ultima_attivita" class="pill pill-green">
                Ultima attività: {{ formatDate(user.ultima_attivita) }}
              </span>
            </div>
            <div class="stats">
              <span class="pill pill-blue">
                Messaggi: {{ user.messaggi_totali ?? 0 }}
              </span>
              <span class="pill pill-gray">ID: {{ user.id }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="card sangmata-card">
  <div class="osint-header">
    <h3> Storico Nomi e Username (SangMata)</h3>
    <button 
      class="btn btn-sm btn-sangmata" 
      @click="searchSangmata" 
      :disabled="loadingSangmata"
    >
      <span v-if="loadingSangmata">Ricerca in corso...</span>
      <span v-else>Cerca Storico Completo</span>
    </button>
  </div>

  <div v-if="sangmataStatus" class="osint-status" :class="sangmataStatus.status">
    {{ sangmataStatus.message }}
  </div>

  <div v-if="sangmataHistory.length" class="history-table-wrapper">
    <table class="table-sm">
      <thead>
        <tr>
          <th>Username</th>
          <th>Nome completo</th>
          <th>Rilevato il</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(h, idx) in sangmataHistory" :key="idx">
          <td class="text-primary">{{ h.username ? '@' + h.username : '—' }}</td>
          <td>{{ h.first_name || '' }} {{ h.last_name || '' }}</td>
          <td class="text-muted">{{ formatDate(h.rilevato_il) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <div v-else-if="!loadingSangmata" class="empty-osint">
    <p class="hint">Nessuna cronologia salvata per questo utente.</p>
  </div>
</div>

      <!-- ==================== OSINT SECTION ==================== -->
      <div class="card osint-card" v-if="user.username">
        <div class="osint-header">
          <h3>OSINT - Presenza Online con username @{{user.username}}</h3>
          <div class="osint-actions">
            <button 
              class="btn btn-sm btn-osint" 
              @click="searchOsint"
              :disabled="loadingOsint"
            >
              <span v-if="loadingOsint"> Ricerca in corso...</span>
              <span v-else> Cerca su Maigret</span>
            </button>
          </div>
        </div>

        <div class="osint-username-info">
          Ricerca per: <strong>@{{ user.username }}</strong>
        </div>

        <!-- Status OSINT -->
        <div v-if="osintStatus" class="osint-status" :class="osintStatus.status">
          {{ osintStatus.message }}
        </div>

        <!-- Loading -->
        <div v-if="loadingOsintReport" class="loading-box">
           Caricamento report...
        </div>

        <!-- Report disponibile -->
        <div v-else-if="osintReport" class="osint-report-available">
          <div class="report-info">
            <span class="report-icon">📄</span>
            <div class="report-details">
              <span class="report-name">{{ osintReport.report_file }}</span>
              <span class="report-date">Generato: {{ formatDate(osintReport.created_at) }}</span>
            </div>
          </div>
          <div class="report-actions">
            <button class="btn btn-sm btn-view" @click="viewReport">
               Visualizza Report
            </button>
            <a :href="reportViewUrl" target="_blank" class="btn btn-sm btn-outline">
               Apri in nuova finestra
            </a>
          </div>
        </div>

        <!-- Empty State -->
        <div v-else class="empty-osint">
          <p>Nessun report OSINT disponibile.</p>
          <p class="hint">Clicca "Cerca su Maigret" per generare un report sulla presenza online dell'username.</p>
        </div>

        <!-- Modal/Iframe per visualizzare il report -->
        <div v-if="showReportModal" class="report-modal-overlay" @click.self="showReportModal = false">
          <div class="report-modal">
            <div class="report-modal-header">
              <h4>Report OSINT - @{{ user.username }}</h4>
              <button class="close-btn" @click="showReportModal = false">✕</button>
            </div>
            <iframe :src="reportViewUrl" class="report-iframe"></iframe>
          </div>
        </div>
      </div>

      <!-- No Username Warning -->
      <div class="card osint-card osint-disabled" v-else>
        <div class="osint-header">
          <h3>🔍 OSINT - Presenza Online</h3>
        </div>
        <div class="empty-osint">
          <p> Questo utente non ha un username Telegram.</p>
          <p class="hint">La ricerca OSINT richiede un username per funzionare.</p>
        </div>
      </div>

      <!-- ==================== CHAT PARTECIPATE ==================== -->
      <div class="card" v-if="chatUtente.length">
        <h3>Chat in cui partecipa</h3>
        <table class="table">
          <thead>
            <tr>
              <th>Nome</th>
              <th>Tipo</th>
              <th>Messaggi</th>
              <th>Prima</th>
              <th>Ultima</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in chatUtente" :key="c.id_chat">
              <td>
                <router-link :to="`/messaggi/${c.id_chat}`">
                  {{ c.nome_chat_tradotto || c.nome_chat }}
                </router-link>
              </td>
              <td>{{ c.tipo }}</td>
              <td>{{ c.messaggi_utente }}</td>
              <td>{{ formatDate(c.prima_interazione) }}</td>
              <td>{{ formatDate(c.ultima_interazione) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- ==================== MESSAGGI RECENTI ==================== -->
      <div class="section-container" v-if="messages.length">
        <h3 class="section-title">Messaggi recenti</h3>
        
        <div class="messages-grid">
          <div
            v-for="msg in messages"
            :key="msg.id_messaggio"
            class="message-card-modern"
          >
            <div class="msg-header">
              <div class="msg-origin">
                <span class="chat-icon">💬</span>
                <span class="chat-name">{{ msg.provenienza_tradotta || msg.provenienza }}</span>
              </div>
              <span class="msg-date">{{ formatDate(msg.data_invio) }}</span>
            </div>

            <div v-if="msg.tipo_evento" class="msg-event-banner">
              {{ eventLabel(msg.tipo_evento) }}
            </div>

            <div class="msg-body">
              <p v-if="msg.testo && msg.testo !== '📎 Allegato'" class="msg-content">
                {{ msg.testo }}
              </p>
              
              <div v-else-if="msg.file_url" class="msg-attachment">
                 📎 Allegato multimediale
              </div>
              <div v-else-if="msg.testo === '📎 Allegato'" class="msg-attachment">
                 📎 Allegato
              </div>

              <div v-if="msg.testo_tradotto || msg.translating" class="translation-box">
                <div v-if="msg.translating" class="translating-loader">
                  <span class="dot"></span> Traduzione in corso...
                </div>
                <div v-else class="translated-text">
                  <span class="lang-flag">🇮🇹</span> {{ msg.testo_tradotto }}
                </div>
              </div>
            </div>

            <div class="msg-actions">
              <button
                v-if="msg.testo && msg.testo !== '📎 Allegato'"
                class="action-btn translate-btn"
                @click.stop="msg.testo_tradotto ? (msg.testo_tradotto = '') : traduci(msg)"
              >
                <span class="icon">🌐</span>
                {{ msg.testo_tradotto ? 'Nascondi' : 'Traduci' }}
              </button>

              <div class="spacer"></div>

              <a 
                href="#" 
                class="telegram-btn"
                :class="{ 'private-group': !isPublicChat(msg) }"
                @click.stop.prevent="gestisciClickTelegram(msg)"
                :title="isPublicChat(msg) ? 'Apri su Telegram' : 'Gruppo Privato'"
              >
                <span class="tg-icon" v-if="isPublicChat(msg)">✈️</span>
                <span class="tg-icon" v-else>🔒</span>
                <span v-if="isPublicChat(msg)">Apri su Telegram</span>
                <span v-else>Mostra in App</span>
              </a>
            </div>
          </div>
        </div>

        <div class="pager-container">
          <button
            class="btn-load-more"
            :disabled="loadingMore || !hasMoreMessages"
            @click="loadMoreMessages"
          >
            {{ loadingMore ? 'Caricamento...' : 'Carica altri messaggi' }}
          </button>
        </div>
      </div>

      <!-- ==================== ALLEGATI ==================== -->
      <div class="card" v-if="allegatiUtente.length">
        <h3>📎 Allegati</h3>
        <ul class="attachments-list">
          <li v-for="a in allegatiUtente" :key="a.id_messaggio">
            <a :href="a.file_url" target="_blank">
              {{ a.media_type }} — {{ a.nome_chat_tradotto || a.nome_chat }}
            </a>
            <small>({{ formatDate(a.data_invio) }})</small>
          </li>
        </ul>
        <div class="pager">
          <button
            class="btn"
            :disabled="loadingMoreAllegati || !hasMoreAllegati"
            @click="loadMoreAllegati"
          >
            Carica altri
          </button>
        </div>
      </div>

      <!-- ==================== REPLY ==================== -->
      <div class="card" v-if="replyUtente.length">
        <h3>💬 Reply a utenti</h3>
        <div class="reply-list">
          <div
            v-for="(r, idx) in limitedReply"
            :key="r.id_messaggio"
            class="reply-card"
          >
            <p class="msg-text">{{ r.reply_text || r.testo }}</p>
            <div class="reply-footer">
              <small>
                → In risposta a
                <router-link
                  v-if="r.reply_to_user_id"
                  :to="`/utenti/${r.reply_to_user_id}`"
                  class="reply-user"
                >
                  @{{ r.reply_to_nome }}
                </router-link>
                <span v-else class="unknown-user">
                  @{{ r.reply_to_nome || "Utente sconosciuto" }}
                </span>
                ({{ r.nome_chat_tradotto || r.nome_chat }}) • {{ formatDate(r.data_invio) }}
              </small>

              <a 
                href="#" 
                class="telegram-btn private-group" 
                style="padding: 0.3rem 0.8rem; font-size: 0.75rem;"
                :class="{ 'private-group': !isPublicChat(r) }"
                @click.stop.prevent="gestisciClickTelegram(r)"
              >
                <span v-if="isPublicChat(r)">✈️ Apri</span>
                <span v-else>🔒 Mostra in App</span>
              </a>
            </div>
          </div>
        </div>

        <div class="see-more" v-if="replyUtente.length > replyLimitLocal">
          <button class="btn" @click="toggleShowAll">
            {{ showAllReplies ? "Mostra meno" : "Mostra altri" }}
          </button>
        </div>
      </div>

      <div style="margin-top: 1rem">
        <button class="btn" @click="$router.push('/utenti')">
          ← Torna alla lista
        </button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: "Utenti",
  data() {
    return {
      utenti: [],
      page: 1,
      limit: 25,
      hasMore: false,
      loading: false,

      user: {},
      messages: [],
      chatUtente: [],
      allegatiUtente: [],
      replyUtente: [],

      msgPage: 1,
      msgLimit: 10,
      hasMoreMessages: false,
      loadingMore: false,

      allegatiPage: 1,
      allegatiLimit: 10,
      hasMoreAllegati: false,
      loadingMoreAllegati: false,

      replyPage: 1,
      replyLimit: 5,
      hasMoreReply: false,
      loadingMoreReply: false,
      showAllReplies: false,

      searchUser: "",
      searchIdGlobal: "",
      searchedChats: [],
      searchError: "",
      searchPerformed: false,

      // OSINT MAIGRET
      osintReport: null,
      loadingOsintReport: false,
      loadingOsint: false,
      osintStatus: null,
      osintPollingInterval: null,
      showReportModal: false,

      // SANGMATA BETA
      sangmataHistory: [],
      loadingSangmata: false,
      sangmataStatus: null,
      sangmataInterval: null,
    };
  },
  computed: {
    userId() {
      return this.$route.params.userId ? Number(this.$route.params.userId) : null;
    },
    filteredUtenti() {
      return this.utenti.filter(
        u => (u.nome && u.nome.trim() !== "") || (u.username && u.username.trim() !== "")
      );
    },
    limitedReply() {
      return this.showAllReplies
        ? this.replyUtente
        : this.replyUtente.slice(0, this.replyLimit);
    },
    replyLimitLocal() {
      return this.replyLimit;
    },
    reportViewUrl() {
      if (!this.user.username) return '';
      return `http://127.0.0.1:5000/api/osint/${this.user.username}/report/view`;
    }
  },
  watch: {
    "$route.params.userId": {
      immediate: true,
      handler() {
        this.init();
      }
    }
  },
  mounted() {
    this.init();
  },
  beforeUnmount() {
    if (this.osintPollingInterval) clearInterval(this.osintPollingInterval);
    if (this.sangmataInterval) clearInterval(this.sangmataInterval);
  },
  methods: {
    init() {
      if (this.userId) {
        this.loadUser();
      } else {
        this.loadList();
      }
    },
    openUser(id) {
      this.$router.push(`/utenti/${id}`);
    },
    async traduci(m) {
      try {
        m.translating = true;
        const res = await fetch(`http://127.0.0.1:5000/api/traduci`, {
          method: "POST",
          body: JSON.stringify({ q: m.testo }),
          headers: { "Content-Type": "application/json" }
        });
        const json = await res.json();
        if (json.translatedText) {
          m.testo_tradotto = json.translatedText;
        }
      } catch (e) {
        console.error("Errore traduzione:", e);
      } finally {
        m.translating = false;
      }
    },
    async loadList(reset = true) {
      if (reset) {
        this.utenti = [];
        this.page = 1;
      }
      this.loading = true;
      try {
        const offset = (this.page - 1) * this.limit;
        const res = await fetch(`http://127.0.0.1:5000/api/utenti?limit=${this.limit}&offset=${offset}`);
        const json = await res.json();
        const nuovi = json.data || [];
        if (!nuovi.length) {
          this.hasMore = false;
        } else {
          this.utenti = [...this.utenti, ...nuovi];
          this.hasMore = json.has_more;
        }
      } catch (e) {
        console.error("Errore caricamento lista utenti:", e);
      } finally {
        this.loading = false;
      }
    },
    changePage(delta) {
      const next = this.page + delta;
      if (next < 1 || this.loading) return;
      this.page = next;
      this.loadList(true);
    },
    async searchUsersUnified() {
      this.searchError = "";
      this.searchPerformed = true;
      if (!this.searchUser.trim()) { this.loadList(); return; }
      try {
        const term = this.searchUser.trim();
        const url = /^\d+$/.test(term)
          ? `http://127.0.0.1:5000/api/cerca?id=${term}`
          : `http://127.0.0.1:5000/api/cerca?q=${encodeURIComponent(term)}`;
        const res = await fetch(url);
        const json = await res.json();
        this.utenti = json?.data?.users || [];
      } catch (e) {
        this.searchError = "Errore durante la ricerca";
      }
    },
    async findChatsByUserId() {
      this.searchError = "";
      this.searchPerformed = true;
      const id = String(this.searchIdGlobal || "").trim();
      if (!/^\d+$/.test(id)) { this.searchError = "ID non valido"; return; }
      try {
        const res = await fetch(`http://127.0.0.1:5000/api/cerca?id=${id}&include_chats=true`);
        const json = await res.json();
        this.searchedChats = json?.data?.chats || [];
      } catch (e) {
        this.searchError = "Errore durante la ricerca";
      }
    },
    async loadUser() {
      try {
        const res = await fetch(`http://127.0.0.1:5000/api/utente/${this.userId}`);
        const json = await res.json();
        if (json.status === "success") {
          this.user = json.user;
          this.chatUtente = json.chats;
          // Inizializza tutte le sezioni di dettaglio
          this.loadSangmataHistory(); 
          this.loadMessages();
          this.loadAllegati();
          this.loadReply();
          if (this.user.username) this.loadOsintReport();
        }
      } catch (e) {
        console.error("Errore caricamento utente:", e);
      }
    },
    
    // --- LOGICA SANGMATA BETA ---
    async loadSangmataHistory() {
      try {
        const res = await fetch(`http://127.0.0.1:5000/api/utente/${this.userId}/storico`);
        const json = await res.json();
        if (json.status === "success") this.sangmataHistory = json.data;
      } catch (e) { console.error(e); }
    },
    async searchSangmata() {
      this.loadingSangmata = true;
      this.sangmataStatus = { status: "loading", message: "⏳ Contatto @SangMata_beta_bot..." };
      try {
        await fetch(`http://127.0.0.1:5000/api/sangmata/search/${this.userId}`, { method: "POST" });
        this.sangmataInterval = setInterval(async () => {
          const res = await fetch(`http://127.0.0.1:5000/api/sangmata/status/${this.userId}`);
          const data = await res.json();
          this.sangmataStatus = data;
          if (['success', 'error', 'not_found'].includes(data.status)) {
            clearInterval(this.sangmataInterval);
            this.loadingSangmata = false;
            if (data.status === 'success') this.loadSangmataHistory();
          }
        }, 3000);
      } catch (e) { 
        this.sangmataStatus = { status: "error", message: "❌ Errore connessione" };
        this.loadingSangmata = false; 
      }
    },

    // --- ALTRI METODI ORIGINALI ---
    async loadMessages() {
      this.loadingMore = true;
      try {
        const offset = (this.msgPage - 1) * this.msgLimit;
        const res = await fetch(`http://127.0.0.1:5000/api/messaggi_utente/${this.userId}?limit=${this.msgLimit}&offset=${offset}`);
        const json = await res.json();
        const nuovi = json.data || [];
        this.messages = this.msgPage === 1 ? nuovi : [...this.messages, ...nuovi];
        this.hasMoreMessages = json.has_more;
      } finally { this.loadingMore = false; }
    },
    loadMoreMessages() { this.msgPage++; this.loadMessages(); },
    
    async loadAllegati() {
      const offset = (this.allegatiPage - 1) * this.allegatiLimit;
      const res = await fetch(`http://127.0.0.1:5000/api/allegati_utente/${this.userId}?limit=${this.allegatiLimit}&offset=${offset}`);
      const json = await res.json();
      this.allegatiUtente = this.allegatiPage === 1 ? json.data : [...this.allegatiUtente, ...json.data];
    },

    async loadReply() {
      const res = await fetch(`http://127.0.0.1:5000/api/reply_utente/${this.userId}?limit=50`);
      const json = await res.json();
      this.replyUtente = json.data || [];
    },

    async searchOsint() {
      this.loadingOsint = true;
      this.osintStatus = { status: "loading", message: "⏳ Avvio Maigret..." };
      await fetch(`http://127.0.0.1:5000/api/osint/${this.user.username}/search`, { method: "POST" });
      this.startOsintPolling();
    },
    startOsintPolling() {
       this.osintPollingInterval = setInterval(async () => {
          const res = await fetch(`http://127.0.0.1:5000/api/osint/${this.user.username}/status`);
          const json = await res.json();
          this.osintStatus = json;
          if (json.status === "success") { 
            clearInterval(this.osintPollingInterval); 
            this.loadOsintReport(); 
            this.loadingOsint = false; 
          }
       }, 5000);
    },
    async loadOsintReport() {
       const res = await fetch(`http://127.0.0.1:5000/api/osint/${this.user.username}/report`);
       const json = await res.json();
       if (json.status === "success") this.osintReport = json;
    },
    viewReport() { this.showReportModal = true; },
    formatDate(d) { return d ? new Intl.DateTimeFormat("it-IT", { dateStyle: "short", timeStyle: "short" }).format(new Date(d)) : "—"; },
    isPublicChat(m) { return !!m.chat_username; },
    getTelegramLink(m) { 
      let id = String(m.id_chat).replace("-100", "");
      return `https://t.me/c/${id}/${m.id_messaggio}`; 
    },
    gestisciClickTelegram(m) { window.open(this.getTelegramLink(m), '_blank'); }
  }
};
</script>

<style scoped>
:root {
  --primary: #1e4fd1;
  --bg-card: #ffffff;
  --bg-hover: #f8fafc;
  --text-main: #1e293b;
  --text-light: #64748b;
  --border: #e2e8f0;
  --radius-lg: 16px;
  --radius-md: 12px;
  --shadow-soft: 0 4px 20px rgba(0, 0, 0, 0.05);
  --shadow-hover: 0 8px 24px rgba(0,0,0,0.08);
  --color-danger: #ef4444;
  --color-success: #16a34a;
  --color-warning: #f59e0b;
}

.page-title {
  font-size: 1.8rem;
  font-weight: 700;
  margin-bottom: 1.8rem;
  color: var(--primary);
  letter-spacing: -0.3px;
  line-height: 1.25;
}

.section-container {
  margin-top: 2rem;
}

.section-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #334155;
  margin-bottom: 1rem;
  padding-left: 0.5rem;
}

.card {
  background: var(--bg-card);
  backdrop-filter: blur(12px);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
  padding: 1.6rem;
  margin: 1.5rem 0;
  transition: all 0.3s ease;
  border: 1px solid var(--border);
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-hover);
}

.header {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}
.avatar-wrapper {
  flex-shrink: 0;
}
.username {
  margin: 0 0 0.5rem 0;
  font-size: 1.4rem;
  color: var(--text-main);
}
.meta {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.8rem;
}
.stats {
  display: flex;
  gap: 0.5rem;
}

.search-bar-group {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 2rem;
  justify-content: center;
}
.input-with-btn {
  display: flex;
  align-items: center;
  gap: .6rem;
}
.input {
  padding: .9rem 1.1rem;
  border-radius: var(--radius-lg);
  border: 1px solid #dbe3f0;
  font-size: 0.95rem;
  background: #fff;
  transition: all 0.25s ease;
  min-width: 220px;
}
.input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(30,79,209,0.12);
  outline: none;
}

.btn {
  padding: .7rem 1.4rem;
  border-radius: var(--radius-lg);
  border: none;
  background: linear-gradient(135deg, #2563eb, #1e40af);
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 600;
  color: #fff;
  transition: all 0.3s ease;
}
.btn:hover {
  background: linear-gradient(135deg, #1d4ed8, #1e3a8a);
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.3);
  transform: translateY(-2px);
}
.btn:disabled { opacity: .5; cursor: not-allowed; transform: none; }

.btn-sm {
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
}

.btn-osint {
  background: linear-gradient(135deg, #7c3aed, #5b21b6);
}
.btn-osint:hover {
  background: linear-gradient(135deg, #6d28d9, #4c1d95);
  box-shadow: 0 6px 14px rgba(124, 58, 237, 0.3);
}

.btn-view {
  background: linear-gradient(135deg, #10b981, #059669);
}
.btn-view:hover {
  background: linear-gradient(135deg, #059669, #047857);
  box-shadow: 0 6px 14px rgba(16, 185, 129, 0.3);
}

.btn-outline {
  background: white;
  color: #475569;
  border: 1px solid #e2e8f0;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}
.btn-outline:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
  box-shadow: none;
  transform: none;
}

.table {
  width: 100%;
  border-collapse: separate; 
  border-spacing: 0;
  background: white;
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-soft);
}
.table th {
  background: #f8fafc;
  color: #64748b;
  font-weight: 600;
  text-transform: uppercase;
  font-size: 0.75rem;
  letter-spacing: 0.05em;
  padding: 1.2rem 1.5rem;
  border-bottom: 1px solid var(--border);
}
.table td {
  padding: 1.2rem 1.5rem;
  border-bottom: 1px solid #f1f5f9;
  color: #334155;
  font-size: 0.95rem;
}
.table tr:last-child td { border-bottom: none; }
.table tr:hover td { background-color: #f8fbff; }
.table a { color: var(--primary); font-weight: 500; text-decoration: none; }
.table a:hover { text-decoration: underline; }
.rowlink { cursor: pointer; }

.avatar, .avatar-xl {
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid #e5eaf0;
  background: #f1f5f9;
}
.avatar { width:44px; height:44px; }
.avatar-xl { width:92px; height:92px; display:block; box-shadow: 0 4px 10px rgba(0,0,0,0.1); border: 4px solid white; }
.avatar-fallback {
  background:linear-gradient(135deg,#2563eb,#1e40af);
  display:flex; align-items:center; justify-content:center;
  font-size: 1rem;
  color:#fff;
  font-weight: 600;
}

/* ==================== OSINT STYLES ==================== */
.osint-card {
  background: linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%);
  border: 1px solid #e9d5ff;
}

.osint-card.osint-disabled {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.osint-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.osint-header h3 {
  margin: 0;
  font-size: 1.2rem;
  color: #5b21b6;
}

.osint-username-info {
  background: white;
  padding: 0.6rem 1rem;
  border-radius: 8px;
  font-size: 0.9rem;
  color: #475569;
  margin-bottom: 1rem;
  border: 1px solid #e9d5ff;
}

.osint-status {
  padding: 0.8rem 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
  font-size: 0.9rem;
}

.osint-status.loading,
.osint-status.processing,
.osint-status.queued {
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fcd34d;
}

.osint-status.success {
  background: #dcfce7;
  color: #166534;
  border: 1px solid #86efac;
}

.osint-status.error,
.osint-status.not_found {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fca5a5;
}

.loading-box {
  text-align: center;
  padding: 2rem;
  color: #64748b;
}

/* Report disponibile */
.osint-report-available {
  background: white;
  border: 1px solid #e9d5ff;
  border-radius: 12px;
  padding: 1.2rem;
}

.report-info {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.report-icon {
  font-size: 2rem;
  background: #f3e8ff;
  padding: 0.8rem;
  border-radius: 10px;
}

.report-details {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.report-name {
  font-weight: 600;
  color: #334155;
}

.report-date {
  font-size: 0.8rem;
  color: #64748b;
}

.report-actions {
  display: flex;
  gap: 0.8rem;
  flex-wrap: wrap;
}

/* Empty State */
.empty-osint {
  text-align: center;
  padding: 2rem;
  color: #64748b;
}

.empty-osint p {
  margin: 0.5rem 0;
}

.empty-osint .hint {
  font-size: 0.85rem;
  color: #94a3b8;
}

/* Modal Report */
.report-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.report-modal {
  background: white;
  border-radius: 16px;
  width: 90%;
  max-width: 1200px;
  height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.report-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.report-modal-header h4 {
  margin: 0;
  color: #334155;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: #64748b;
  padding: 0.5rem;
  line-height: 1;
}
.close-btn:hover {
  color: #ef4444;
}

.report-iframe {
  flex: 1;
  border: none;
  width: 100%;
}

/* --- MESSAGGI CARD MODERN --- */
.messages-grid {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.message-card-modern {
  background: white;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
  padding: 0; 
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  overflow: hidden;
}

.message-card-modern:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.08);
  border-color: #cbd5e1;
}

.msg-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background: #f8fafc;
  border-bottom: 1px solid #f1f5f9;
}

.msg-origin {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  color: #0f172a;
  font-size: 0.95rem;
}

.chat-icon { font-size: 1rem; }

.msg-date {
  font-size: 0.8rem;
  color: #94a3b8;
  font-family: monospace;
}

.msg-body {
  padding: 1.5rem;
  color: #334155;
  font-size: 1rem;
  line-height: 1.6;
}

.msg-content { margin: 0; white-space: pre-wrap; }

.msg-attachment {
  display: inline-block;
  background: #f1f5f9;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-size: 0.9rem;
  color: #475569;
  font-weight: 500;
}

.translation-box {
  margin-top: 1rem;
  background: #eff6ff;
  border-left: 3px solid #3b82f6;
  padding: 0.8rem 1rem;
  border-radius: 0 8px 8px 0;
  font-size: 0.95rem;
  color: #1e3a8a;
}
.lang-flag { margin-right: 0.3rem; }

.msg-actions {
  padding: 0.8rem 1.5rem;
  border-top: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  gap: 1rem;
  background: white;
}

.spacer { flex: 1; }

.action-btn {
  background: transparent;
  border: none;
  color: #64748b;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.8rem;
  border-radius: 6px;
  transition: all 0.2s;
}

.action-btn:hover { background: #f1f5f9; color: #334155; }
.action-btn.translate-btn:hover { color: var(--primary); background: #eef2ff; }

.telegram-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  background-color: #0088cc;
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 99px;
  font-size: 0.85rem;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.2s ease;
  box-shadow: 0 2px 5px rgba(0, 136, 204, 0.25);
}
.telegram-btn:hover {
  background-color: #0077b5;
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 136, 204, 0.35);
}
.telegram-btn.private-group {
  background-color: #fff7ed;
  color: #ea580c;
  border: 1px solid #fdba74;
  box-shadow: none;
}
.telegram-btn.private-group:hover {
  background-color: #ea580c;
  color: white;
  border-color: #ea580c;
}

.msg-event-banner {
  background: #fffbeb;
  color: #b45309;
  font-size: 0.85rem;
  padding: 0.5rem 1.5rem;
  border-bottom: 1px solid #fef3c7;
  font-weight: 600;
}

.reply-card {
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: .8rem;
  margin-bottom: .8rem;
}
.reply-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.reply-user {
  color: var(--primary);
  font-weight: 600;
  text-decoration: underline;
}
.unknown-user { color: #94a3b8; font-style: italic; }

.pager-container { margin-top: 1.5rem; text-align: center; }
.pager { display: flex; align-items: center; gap: .8rem; margin-top: 1rem; justify-content: center; }

.btn-load-more {
  background: white;
  border: 1px solid var(--border);
  color: var(--primary);
  padding: 0.8rem 2rem;
  border-radius: 99px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}
.btn-load-more:hover:not(:disabled) {
  border-color: var(--primary);
  background: #f8fbff;
  transform: translateY(-1px);
}
.btn-load-more:disabled { opacity: 0.6; cursor: not-allowed; }

.pill { padding:.35rem .9rem; border-radius:999px; font-size:.75rem; font-weight:600; }
.pill-blue { background:#dbeafe; color:#1e40af; }
.pill-green { background:#dcfce7; color:#166534; }
.pill-gray { background:#f1f5f9; color:#475569; }
.pill-orange { background:#fff7ed; color:#d97706; border:1px solid #fcd34d; }

.error-msg { color: var(--color-danger); font-weight: 600; margin-top: 0.5rem; }
.see-more { margin-top: 1rem; text-align: center; }

.attachments-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.attachments-list li {
  padding: 0.5rem 0;
  border-bottom: 1px solid #f1f5f9;
}
.attachments-list li:last-child {
  border-bottom: none;
}
.attachments-list a {
  color: var(--primary);
  text-decoration: none;
  font-weight: 500;
}
.attachments-list a:hover {
  text-decoration: underline;
}
.attachments-list small {
  color: #64748b;
  margin-left: 0.5rem;
}
.sangmata-card {
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border-color: #bae6fd;
}
.btn-sangmata {
  background: linear-gradient(135deg, #0284c7, #0369a1);
  color: white;
}
.history-table-wrapper {
  margin-top: 1rem;
  background: white;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e0f2fe;
}
.table-sm {
  width: 100%;
  font-size: 0.85rem;
  border-collapse: collapse;
}
.table-sm th {
  text-align: left;
  padding: 0.8rem;
  background: #f8fafc;
  border-bottom: 2px solid #e0f2fe;
}
.table-sm td {
  padding: 0.7rem 0.8rem;
  border-bottom: 1px solid #f1f5f9;
}
.text-primary { color: #0284c7; font-weight: 600; }
.text-muted { color: #64748b; font-size: 0.75rem; }
</style>