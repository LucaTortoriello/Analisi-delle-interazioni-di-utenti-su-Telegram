<template>
  <div class="app-section chats-page">
    <header class="app-page-header">
      <div>
        <span class="app-eyebrow">Conversation intelligence</span>
        <h1 class="page-title">Chat analizzate</h1>
        <p class="app-page-description">Consulta gruppi e canali importati, amministratori e stato dell'ultima scansione.</p>
      </div>
    </header>

    <div class="filter-row">
      <label for="categoria">Categoria:</label>
      <select
        v-model="categoriaSelezionata"
        @change="onCategoryChange"
        class="select-cat"
      >
        <option value="">Tutte</option>
        <option
          v-for="c in categorie.filter(cat => cat.categoria_chat)"
          :key="c.categoria_chat"
          :value="c.categoria_chat"
        >
          {{ c.categoria_chat }}
        </option>
      </select>
    </div>

    <div class="chat-list">
      <div
        v-for="c in visibleChats"
        :key="c.id_chat"
        class="chat-item card"
        @click="openChat(c.id_chat)"
      >

        <div class="avatar-wrapper">
          <img
            v-if="c.avatar_url"
            :src="c.avatar_url"
            alt="avatar"
            class="avatar"
          />

          <svg v-else class="avatar-placeholder" viewBox="0 0 24 24">
            <circle cx="12" cy="8" r="4" />
            <path d="M4 20c0-4 4-6 8-6s8 2 8 6" />
          </svg>
        </div>

        <div class="chat-main">
          <div class="chat-title-row">
            <h3 class="chat-title">
              {{ c.nome_chat_tradotto || c.nome_chat }}
            </h3>

            <span
              class="pill"
              :class="c.tipo === 'canale' ? 'pill-blue' : 'pill-green'"
            >
              {{ c.tipo }}
            </span>
          </div>

          <div class="chat-admins" v-if="c.admins && c.admins.length > 0">
            <span class="admin-icon" title="Amministratori">🛡️</span>

            <div class="admin-list">
              <span
                v-for="(admin, index) in c.admins.slice(0, 2)"
                :key="admin.id"
                class="admin-link"
                @click.stop="goToUser(admin.id)"
                :title="'ID: ' + admin.id"
              >
                {{ admin.nome || admin.username || 'Admin' }}
                <span v-if="index < Math.min(c.admins.length, 2) - 1">, </span>
              </span>

              <span
                v-if="c.admins.length > 2"
                class="admin-more"
              >
                +{{ c.admins.length - 2 }} altri
              </span>
            </div>
          </div>

          <div class="chat-sub">
            <span
              class="activity-dot"
              :class="{ active: isChatActive(c), inactive: !isChatActive(c) }"
              :title="isChatActive(c) ? 'Attivo' : 'Inattivo'"
            ></span>

            Ultima scansione:
            <strong>
              {{ formatDate(c.ultima_scansione || c.data_importazione) }}
            </strong>
          </div>
        </div>

      </div>
    </div>

    <div v-if="!loading && chats.length === 0" class="empty">
      Nessuna chat trovata.
    </div>

    <div class="see-all" v-if="!showAll && chats.length > 6">
      <button class="btn" @click="showAll = true">Vedi tutte →</button>
    </div>

    <div class="pager" v-if="showAll">
      <button class="btn" :disabled="page <= 1 || loading" @click="changePage(-1)">
        ← Prev
      </button>

      <span>Pagina {{ page }}</span>

      <button class="btn" :disabled="!hasMore || loading" @click="changePage(1)">
        Next →
      </button>
    </div>

  </div>
</template>

<script>
export default {
  name: "Chat",
  data() {
    return {
      chats: [],
      categorie: [],
      categoriaSelezionata: "",
      page: 1,
      limit: 25,
      hasMore: false,
      loading: false,
      showAll: false,
    };
  },

  mounted() {
    this.loadCategorie();
    this.loadChats();
  },

  computed: {
    visibleChats() {
      return this.showAll ? this.chats : this.chats.slice(0, 6);
    },
  },

  methods: {
    isChatActive(chat) {
      if (!chat.ultima_scansione) return false;

      const lastScan = new Date(chat.ultima_scansione + "Z");
      const now = new Date();

      const diffDays =
        (now.getTime() - lastScan.getTime()) /
        (1000 * 60 * 60 * 24);

      return diffDays <= 30;
    },

    goToUser(userId) {
    this.$router.push({ name: 'UtenteDettaglio', params: { userId: userId } });
    },



    async loadCategorie() {
      try {
        const res = await fetch("http://127.0.0.1:5000/api/chat_per_categoria");
        const json = await res.json();
        if (json.status === "success") this.categorie = json.data;
      } catch (e) {
        console.error("Errore categorie", e);
      }
    },

    async loadChats() {
      this.loading = true;
      try {
        const offset = (this.page - 1) * this.limit;
        let url = `http://127.0.0.1:5000/api/chats?limit=${this.limit}&offset=${offset}`;

        if (this.categoriaSelezionata) {
          url += `&categoria=${encodeURIComponent(this.categoriaSelezionata)}`;
        }

        const res = await fetch(url);
        const json = await res.json();

        this.chats = json.data || [];
        this.hasMore = !!json.has_more;

      } catch (e) {
        console.error(e);
        this.chats = [];
        this.hasMore = false;

      } finally {
        this.loading = false;
      }
    },

    onCategoryChange() {
      this.page = 1;
      this.loadChats();
    },

    changePage(delta) {
      this.page += delta;
      this.loadChats();
    },

    openChat(id) {
      this.$router.push(`/messaggi/${id}`);
    },

    formatDate(d) {
      if (!d) return "—";
      const dt = new Date(d + "Z");
      return isNaN(dt) ? d : dt.toLocaleString("it-IT");
    },
  },
};
</script>
<style scoped>
:root {
  --chat-primary: #3558ff;
  --chat-primary-hover: #2847d9;
  --chat-bg: #f8fafc;
  --chat-card-bg: #ffffff;
  --chat-border: #e2e8f0;
  --chat-text: #1e293b;
  --chat-text-muted: #64748b;
  --chat-shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.05);
  --chat-shadow-md: 0 4px 12px rgba(0, 0, 0, 0.08);
  --chat-shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.12);
  --chat-radius: 12px;
  --chat-transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

/* TITOLI */
.page-title {
  font-size: clamp(2rem, 3vw, 2.65rem);
  font-weight: 700;
  color: var(--chat-text);
  margin: 0 0 0.35rem;
  letter-spacing: -0.04em;
  line-height: 1.08;
}

/* FILTRO CATEGORIE */
.filter-row {
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.9rem 1rem;
  background: var(--chat-card-bg);
  border-radius: 15px;
  box-shadow: 0 4px 18px rgba(15,23,42,0.045);
  border: 1px solid var(--chat-border);
  transition: var(--chat-transition);
}

.filter-row:hover {
  box-shadow: var(--chat-shadow-md);
  border-color: #cbd5e1;
}

.filter-row label {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--chat-text);
  white-space: nowrap;
  letter-spacing: 0.3px;
}

.select-cat {
  height: 42px;
  padding: 0 2.5rem 0 0.85rem;
  border-radius: 9px;
  border: 1px solid #dbe3ed;
  background-color: #f8fafc;
  font-size: 0.95rem;
  font-weight: 500;
  color: var(--chat-text);
  outline: none;
  transition: var(--chat-transition);
  min-width: 200px;
  box-shadow: none;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml;utf8,<svg fill='%23475569' height='20' viewBox='0 0 24 24' width='20' xmlns='http://www.w3.org/2000/svg'><path d='M7 10l5 5 5-5z'/></svg>");
  background-repeat: no-repeat;
  background-position: right 0.75rem center;
  background-size: 1.25rem;
}

.select-cat:hover {
  border-color: #94a3b8;
  box-shadow: var(--chat-shadow-md);
  transform: translateY(-1px);
}

.select-cat:focus {
  border-color: var(--chat-primary);
  box-shadow: 0 0 0 4px rgba(53, 88, 255, 0.1);
  transform: translateY(-1px);
}

/* LISTA CHAT */
.chat-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 0.8rem;
  margin-bottom: 1rem;
}

.chat-item {
  background: var(--chat-card-bg);
  min-height: 122px;
  margin: 0;
  border-radius: 14px;
  padding: 1rem;
  cursor: pointer;
  transition: var(--chat-transition);
  border: 1px solid #e2e8f0;
  box-shadow: 0 3px 12px rgba(15,23,42,0.04);
  position: relative;
  overflow: hidden;

  display: flex;
  align-items: center;
  gap: 1rem;
}

/* BARRA COLORE HOVER */
.chat-item::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--chat-primary), #6366f1);
  opacity: 0;
  transition: opacity 0.3s ease;
}

.chat-item:hover::before {
  opacity: 1;
}

.chat-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px rgba(15,23,42,0.08);
  border-color: #c7d2fe;
}

.chat-item:active {
  transform: translateY(-2px);
}

/* CONTENITORE TESTO */
.chat-main {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
}

.chat-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.chat-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--chat-text);
  margin: 0;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.chat-sub {
  font-size: 0.85rem;
  color: var(--chat-text-muted);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.chat-sub strong {
  color: var(--chat-text);
  font-weight: 600;
}

/* PILL */
.pill {
  padding: 0.35rem 0.75rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.3px;
  white-space: nowrap;
  transition: var(--chat-transition);
  text-transform: uppercase;
}

.pill-blue {
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
  color: #1e40af;
  border: 1px solid #93c5fd;
}

.pill-green {
  background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
  color: #065f46;
  border: 1px solid #6ee7b7;
}

.chat-item:hover .pill {
  transform: scale(1.05);
}

/* ATTIVITÀ */
.activity-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
}

.activity-dot.active {
  background-color: #10b981;
  box-shadow: 0 0 0 2px #d1fae5;
}

.activity-dot.inactive {
  background-color: #f59e0b;
  box-shadow: 0 0 0 2px #fffbeb;
}

/* STATO VUOTO */
.empty {
  text-align: center;
  padding: 4rem 2rem;
  color: var(--chat-text-muted);
  font-size: 1rem;
  background: var(--chat-card-bg);
  border-radius: var(--chat-radius);
  border: 2px dashed var(--chat-border);
}

.empty::before {
  content: '📭';
  display: block;
  font-size: 3rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

/* BOTTONI */
.btn {
  padding: 0.75rem 1.5rem;
  border-radius: 10px;
  border: none;
  background: linear-gradient(135deg, var(--chat-primary), #4f46e5);
  color: white;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--chat-transition);
  box-shadow: 0 4px 12px rgba(53, 88, 255, 0.25);
  letter-spacing: 0.3px;
}

.btn:hover {
  background: linear-gradient(135deg, var(--chat-primary-hover), #4338ca);
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(53, 88, 255, 0.35);
}

.btn:active {
  transform: translateY(0);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* PAGINAZIONE */
.see-all {
  text-align: center;
  margin: 2rem 0;
}

.see-all .btn {
  background: linear-gradient(135deg, #ffffff, #f8fafc);
  color: var(--chat-primary);
  border: 2px solid var(--chat-primary);
  box-shadow: none;
}

.see-all .btn:hover {
  background: var(--chat-primary);
  color: white;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1.5rem;
  margin-top: 2rem;
  padding: 1.5rem;
  background: var(--chat-card-bg);
  border-radius: var(--chat-radius);
  box-shadow: var(--chat-shadow-sm);
}

.pager span {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--chat-text);
  padding: 0 1rem;
}

/* RESPONSIVE */
@media (max-width: 768px) {
  .chat-list {
    grid-template-columns: 1fr;
    gap: 1rem;
  }

  .page-title {
    font-size: 1.5rem;
    margin-bottom: 1.5rem;
  }

  .filter-row {
    flex-direction: column;
    align-items: stretch;
  }

  .select-cat {
    width: 100%;
  }

  .pager {
    flex-direction: column;
    gap: 1rem;
  }

  .pager .btn {
    width: 100%;
  }
}

/* ANIMAZIONE */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.chat-item {
  animation: fadeInUp 0.4s ease-out;
  animation-fill-mode: both;
}

.chat-item:nth-child(1) { animation-delay: 0.05s; }
.chat-item:nth-child(2) { animation-delay: 0.1s; }
.chat-item:nth-child(3) { animation-delay: 0.15s; }
.chat-item:nth-child(4) { animation-delay: 0.2s; }
.chat-item:nth-child(5) { animation-delay: 0.25s; }
.chat-item:nth-child(6) { animation-delay: 0.3s; }

/* AVATAR */
.avatar-wrapper {
  width: 50px;
  height: 50px;
}

.avatar,
.avatar-placeholder {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  object-fit: cover;
}

.avatar-placeholder {
  fill: #777;
  background: #e0e0e0;
  padding: 8px;
}

.chat-admins {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 4px 0;
  font-size: 0.8rem;
  color: #64748b; /* var(--chat-text-muted) */
  background-color: #f1f5f9;
  padding: 4px 8px;
  border-radius: 6px;
  width: fit-content;
}

.admin-icon {
  font-size: 0.9rem;
}

.admin-list {
  display: flex;
  white-space: nowrap; /* Evita che i nomi vadano a capo male */
  gap: 4px;
}

.admin-link {
  color: #3558ff; /* var(--chat-primary) */
  font-weight: 500;
  cursor: pointer;
}

.admin-link:hover {
  text-decoration: underline;
}

.admin-more {
  background: #e2e8f0;
  color: #64748b;
  padding: 0 5px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

</style>
