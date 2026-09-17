<template>
  <div class="graph-filtrato-page">
    <h1 class="page-title">
      Interazioni tra utenti per "<span class="kw">{{ keyword }}</span>"
    </h1>

    <div v-if="stats" class="stats-box">
      <div class="stat-item">👥 {{ stats.nodes }} nodi</div>
      <div class="stat-item keyword-item">
        🔗 {{ stats.keyword_edges }} relazioni con keyword
      </div>
    </div>

    <div class="legenda-box">
      <div class="legend-item">
        <span class="legend-dot keyword-dot"></span> Utente che usa la keyword (Scrittore attivo)
      </div>
      <div class="legend-item">
        <span class="legend-dot normal-dot"></span> Utente senza keyword (Contesto relazionale)
      </div>
      <hr style="margin: 8px 0; border-color: #eee;" />
      <div class="legend-item">
        <span class="legend-line keyword-line"></span> Arco: Relazione di reply che contiene la keyword
      </div>
    </div>

    <!-- Barra di ricerca per esplorare nodi -->
    <div class="search-bar">
      <select v-model="selectedCategory" @change="reloadGraph" class="category-select">
    <option value=""> Tutte le categorie</option>
    <option v-for="cat in categories" :key="cat.categoria_chat" :value="cat.categoria_chat">
      {{ cat.categoria_chat }} ({{ cat.totale }})
    </option>
  </select>
      <input
        v-model="focusQuery"
        class="search-input"
        type="text"
        placeholder="🔎 Esplora un utente specifico nel grafo keyword..."
        @keyup.enter="exploreFocusNode"
      />
      <div class="depth-box">
        <input
          v-model.number="depth"
          class="depth-input"
          type="number"
          min="1"
          placeholder="Profondità"
        />
        <small class="depth-label">Nodi da esplorare</small>
      </div>
      <button @click="exploreFocusNode" class="search-btn">Esplora</button>
    </div>

    <div v-if="loading" class="loading-overlay">
      <div class="spinner"></div>
      <p>Caricamento grafo...</p>
    </div>

    <div class="graph-container" ref="network"></div>

    <!-- MODAL DETTAGLIO NODO -->
    <div v-if="selectedNode" class="modal-overlay" @click.self="closeDetails">
      <div class="modal">
        <h3>
          Dettagli utente
          <span class="badge Utente">Utente</span>
          <span v-if="getNodeExploredDepth(selectedNode.id)" class="badge explored">
            Esplorato ({{ getNodeExploredDepth(selectedNode.id) }})
          </span>
        </h3>

        <p><strong>ID:</strong> {{ selectedNode.id.replace("user_", "") }}</p>
        <p><strong>Username:</strong> {{ nodeDetails?.username || "sconosciuto" }}</p>
        <p><strong>Nome:</strong> {{ nodeDetails?.nome || "-" }}</p>
        <p><strong>Ultima attività:</strong> {{ nodeDetails?.ultima_attivita || "-" }}</p>
        <p><strong>Messaggi totali:</strong> {{ nodeDetails?.messaggi_totali || 0 }}</p>

        <p class="keyword-highlight-box">
          🔍 <strong>Keyword:</strong> "{{ keyword }}"
          <span class="badge keyword">
            {{ keywordStats[selectedNodeId] || 0 }} occorrenze
          </span>
        </p>

        <!-- ✅ RIEPILOGO INTERAZIONI REPLY (come Grafo.vue) -->
        <div v-if="nodeReplySummary && (nodeReplySummary.sent.length || nodeReplySummary.received.length)" class="reply-summary-section">
          <h4>📊 Riepilogo Interazioni Reply (con keyword)</h4>
          
          <!-- Reply INVIATI -->
          <div v-if="nodeReplySummary.sent.length" class="reply-direction-box sent-box">
            <p class="direction-label" @click="toggleSentExpanded" style="cursor: pointer;">
              <span class="arrow-icon">→</span> 
              <strong>Ha risposto a</strong>
              <span class="total-badge">{{ nodeReplySummary.totalSent }} reply</span>
              <span class="expand-icon">{{ sentExpanded ? '▼' : '▶' }}</span>
            </p>
            
            <ul class="interaction-list">
              <li v-for="(item, idx) in nodeReplySummary.sent.slice(0, 5)" :key="'sent-'+idx"
                  @click.stop="toggleUserReplies('sent', item)"
                  class="interaction-item-clickable">
                <span class="interaction-name">{{ item.nome }}</span>
                <span class="interaction-count">{{ item.count }}</span>
                <span class="expand-arrow">{{ isUserExpanded('sent', item.id) ? '▼' : '▶' }}</span>
              </li>
            </ul>
            
            <template v-for="(item, idx) in nodeReplySummary.sent.slice(0, 5)" :key="'sent-detail-'+idx">
              <div v-if="isUserExpanded('sent', item.id)" class="reply-detail-box">
                <div v-if="loadingUserReplies === 'sent-'+item.id" class="loading-mini">⏳ Caricamento...</div>
                <ul v-else-if="userRepliesCache['sent-'+item.id]" class="reply-messages-list">
                  <li v-for="(msg, mIdx) in userRepliesCache['sent-'+item.id].slice(0, 3)" :key="'msg-'+mIdx">
                    <div class="mini-msg">
                      <span class="mini-date">{{ formatDate(msg.data_invio) }}</span>
                      <span class="mini-chat">{{ msg.nome_chat_tradotto || msg.nome_chat }}</span>
                      <a href="#" class="tg-link-mini" @click.stop.prevent="gestisciClickTelegram(msg)">
                        {{ isPublicChat(msg) ? '✈️' : '🔒' }}
                      </a>
                    </div>
                    <p class="mini-text" v-html="highlightKeyword(msg.reply_text || msg.testo)"></p>
                  </li>
                  <li v-if="userRepliesCache['sent-'+item.id].length > 3" class="more-messages">
                    ... e altri {{ userRepliesCache['sent-'+item.id].length - 3 }} messaggi
                  </li>
                </ul>
              </div>
            </template>
            
            <p v-if="nodeReplySummary.sent.length > 5 && !sentExpanded" class="more-items-link" @click="toggleSentExpanded">
              ▶ ... e altri {{ nodeReplySummary.sent.length - 5 }} utenti
            </p>
            
            <template v-if="sentExpanded && nodeReplySummary.sent.length > 5">
              <ul class="interaction-list expanded-list">
                <li v-for="(item, idx) in nodeReplySummary.sent.slice(5)" :key="'sent-exp-'+idx"
                    @click.stop="toggleUserReplies('sent', item)"
                    class="interaction-item-clickable">
                  <span class="interaction-name">{{ item.nome }}</span>
                  <span class="interaction-count">{{ item.count }}</span>
                  <span class="expand-arrow">{{ isUserExpanded('sent', item.id) ? '▼' : '▶' }}</span>
                </li>
              </ul>
              <p class="more-items-link" @click="toggleSentExpanded">▲ Nascondi</p>
            </template>
          </div>

          <!-- Reply RICEVUTI -->
          <div v-if="nodeReplySummary.received.length" class="reply-direction-box received-box">
            <p class="direction-label" @click="toggleReceivedExpanded" style="cursor: pointer;">
              <span class="arrow-icon">←</span> 
              <strong>Ha ricevuto reply da</strong>
              <span class="total-badge">{{ nodeReplySummary.totalReceived }} reply</span>
              <span class="expand-icon">{{ receivedExpanded ? '▼' : '▶' }}</span>
            </p>
            
            <ul class="interaction-list">
              <li v-for="(item, idx) in nodeReplySummary.received.slice(0, 5)" :key="'recv-'+idx"
                  @click.stop="toggleUserReplies('received', item)"
                  class="interaction-item-clickable">
                <span class="interaction-name">{{ item.nome }}</span>
                <span class="interaction-count">{{ item.count }}</span>
                <span class="expand-arrow">{{ isUserExpanded('received', item.id) ? '▼' : '▶' }}</span>
              </li>
            </ul>
            
            <template v-for="(item, idx) in nodeReplySummary.received.slice(0, 5)" :key="'recv-detail-'+idx">
              <div v-if="isUserExpanded('received', item.id)" class="reply-detail-box">
                <div v-if="loadingUserReplies === 'received-'+item.id" class="loading-mini">⏳ Caricamento...</div>
                <ul v-else-if="userRepliesCache['received-'+item.id]" class="reply-messages-list">
                  <li v-for="(msg, mIdx) in userRepliesCache['received-'+item.id].slice(0, 3)" :key="'msg-recv-'+mIdx">
                    <div class="mini-msg">
                      <span class="mini-date">{{ formatDate(msg.data_invio) }}</span>
                      <span class="mini-chat">{{ msg.nome_chat_tradotto || msg.nome_chat }}</span>
                      <a href="#" class="tg-link-mini" @click.stop.prevent="gestisciClickTelegram(msg)">
                        {{ isPublicChat(msg) ? '✈️' : '🔒' }}
                      </a>
                    </div>
                    <p class="mini-text" v-html="highlightKeyword(msg.reply_text || msg.testo)"></p>
                  </li>
                  <li v-if="userRepliesCache['received-'+item.id].length > 3" class="more-messages">
                    ... e altri {{ userRepliesCache['received-'+item.id].length - 3 }} messaggi
                  </li>
                </ul>
              </div>
            </template>
            
            <p v-if="nodeReplySummary.received.length > 5 && !receivedExpanded" class="more-items-link" @click="toggleReceivedExpanded">
              ▶ ... e altri {{ nodeReplySummary.received.length - 5 }} utenti
            </p>
            
            <template v-if="receivedExpanded && nodeReplySummary.received.length > 5">
              <ul class="interaction-list expanded-list">
                <li v-for="(item, idx) in nodeReplySummary.received.slice(5)" :key="'recv-exp-'+idx"
                    @click.stop="toggleUserReplies('received', item)"
                    class="interaction-item-clickable">
                  <span class="interaction-name">{{ item.nome }}</span>
                  <span class="interaction-count">{{ item.count }}</span>
                  <span class="expand-arrow">{{ isUserExpanded('received', item.id) ? '▼' : '▶' }}</span>
                </li>
              </ul>
              <p class="more-items-link" @click="toggleReceivedExpanded">▲ Nascondi</p>
            </template>
          </div>

          <div class="reply-balance" :class="balanceClass">{{ balanceText }}</div>
        </div>

        <div v-if="nodeReplySummaryLoading" class="loading-summary">⏳ Caricamento interazioni...</div>

        <h4>Messaggi con keyword "{{ keyword }}" (Non Reply)</h4>
        <p v-if="keywordMessages.length === 0">Nessun messaggio contenente la keyword.</p>
        <ul v-else class="reply-list">
          <li v-for="m in keywordMessages.slice(0, 5)" :key="m.id_messaggio">
            <div class="msg-meta-row">
              <em>{{ m.data_invio }}</em> —
              <strong>{{ m.provenienza_tradotta || m.provenienza }}</strong>
              <a href="#" class="tg-link" :class="{ 'tg-private': !isPublicChat(m) }"
                 @click.stop.prevent="gestisciClickTelegram(m)">
                <span v-if="isPublicChat(m)">✈️</span><span v-else>🔒</span>
              </a>
            </div>
            <p v-html="highlightKeyword(m.testo)"></p>
          </li>
          <li v-if="keywordMessages.length > 5" class="more-items">
            ... e altri {{ keywordMessages.length - 5 }} messaggi
          </li>
        </ul>

        <h4>Chat frequentate</h4>
        <ul class="reply-list">
          <li v-for="c in userChats.slice(0, 5)" :key="c.id_chat">
            <strong>{{ c.nome_chat_tradotto || c.nome_chat }}</strong>
            — {{ c.messaggi_utente }} messaggi
          </li>
          <li v-if="userChats.length > 5" class="more-items">
            ... e altre {{ userChats.length - 5 }} chat
          </li>
        </ul>

        <router-link :to="{ name: 'UtenteDettaglio', params: { userId: selectedNode.id.replace('user_', '') } }" class="username-link">
          Vai al dettaglio utente
        </router-link>
        <button class="btn-close" @click="closeDetails">Chiudi</button>
      </div>
    </div>

    <!-- MODAL DETTAGLIO ARCO -->
    <div v-if="selectedEdge" class="modal-overlay" @click.self="closeDetails">
      <div class="modal">
        <h3>Dettagli reply (bidirezionale)</h3>

        <p class="keyword-ref">
          🔍 <strong>Keyword:</strong> "{{ keyword }}"
        </p>

        <!-- Riepilogo visivo A ↔ B -->
        <div class="edge-summary-visual">
          <div class="edge-user">
            <div class="avatar-placeholder">👤</div>
            <span class="edge-user-name">{{ selectedEdge.fromNome || selectedEdge.from?.replace('user_', '') }}</span>
          </div>
          
          <div class="edge-arrow-container">
            <div class="edge-direction" v-if="edgeDirectionStats">
              <span class="direction-count out">{{ edgeDirectionStats.aToB }} →</span>
            </div>
            <div class="edge-total">{{ edgeDirectionStats ? edgeDirectionStats.total : selectedEdge.value }}</div>
            <div class="edge-direction" v-if="edgeDirectionStats">
              <span class="direction-count in">← {{ edgeDirectionStats.bToA }}</span>
            </div>
          </div>
          
          <div class="edge-user">
            <div class="avatar-placeholder">👤</div>
            <span class="edge-user-name">{{ selectedEdge.toNome || selectedEdge.to?.replace('user_', '') }}</span>
          </div>
        </div>

        <p><strong>Occorrenze keyword in questa relazione:</strong> 
          <span class="badge keyword">{{ selectedEdge.keyword_total || 0 }}</span>
        </p>

        <h4>Messaggi rilevanti con keyword</h4>

        <ul v-if="edgeMessages.length" class="reply-list">
          <li v-for="m in edgeMessages.slice(0, 5)" :key="m.id_messaggio">
            <div class="msg-meta-row">
              <strong>{{ m.autore_nome }}</strong>
              — <em>{{ m.data_invio }}</em>
              — <strong>{{ m.nome_chat_tradotto || m.nome_chat }}</strong>
              <a href="#" class="tg-link" :class="{ 'tg-private': !isPublicChat(m) }"
                 @click.stop.prevent="gestisciClickTelegram(m)">
                <span v-if="isPublicChat(m)">✈️</span><span v-else>🔒</span>
              </a>
            </div>

            <p>
              <strong>Occ. reply:</strong> {{ m.keyword_count_reply || 0 }} |
              <strong>Occ. originale:</strong> {{ m.keyword_count_original || 0 }}
            </p>

            <p><strong>Reply:</strong></p>
            <p class="msg-text" v-html="highlightKeyword(m.reply_text)"></p>

            <p v-if="m.original_text">
              <strong>Originale:</strong>
              <span class="msg-text" v-html="highlightKeyword(m.original_text)"></span>
            </p>
          </li>
        </ul>
        <p v-else>Nessun messaggio trovato per questa relazione.</p>

        <button class="btn-close" @click="closeDetails">Chiudi</button>
      </div>
    </div>

    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>

<script>
import { Network } from "vis-network";
import { DataSet } from "vis-data";

export default {
  name: "GrafoFiltrato",
  data() {
    return {
      keyword: "",
      focusQuery: "",
      depth: 5,
      toast: "",
      
      nodesDS: null,
      edgesDS: null,
      network: null,
      loading: false,

      stats: null,
      keywordStats: {},

      selectedNode: null,
      selectedEdge: null,
      selectedNodeId: null,

      nodeDetails: null,
      userChats: [],
      keywordMessages: [],
      edgeMessages: [],
      edgeDirectionStats: null,

      // Tracciamento profondità (come Grafo.vue)
      exploredNodesDepth: {},
      
      // Riepilogo reply (come Grafo.vue)
      nodeReplySummary: null,
      nodeReplySummaryLoading: false,
      
      // Tendine espandibili
      sentExpanded: false,
      receivedExpanded: false,
      expandedUsers: new Set(),
      userRepliesCache: {},
      loadingUserReplies: null,

      // Cache
      nodeCache: {},
      currentLoadingId: null,
      clickTimer: null,

      categories: [],
      selectedCategory: "",
    };
  },

  computed: {
    balanceClass() {
      if (!this.nodeReplySummary) return '';
      const diff = this.nodeReplySummary.totalSent - this.nodeReplySummary.totalReceived;
      if (diff > 0) return 'balance-positive';
      if (diff < 0) return 'balance-negative';
      return 'balance-neutral';
    },
    balanceText() {
      if (!this.nodeReplySummary) return '';
      const sent = this.nodeReplySummary.totalSent;
      const recv = this.nodeReplySummary.totalReceived;
      const diff = sent - recv;
      if (diff > 0) return `📤 Invia più di quanto riceve (+${diff})`;
      if (diff < 0) return `📥 Riceve più di quanto invia (${diff})`;
      return `⚖️ Bilancio equilibrato`;
    }
  },
  
  async fetchCategories() {
    try {
      const res = await fetch("http://127.0.0.1:5000/api/chat_per_categoria");
      if (res.ok) {
        const json = await res.json();
        this.categories = json.data || [];
      }
    } catch (e) {
      console.error("Errore caricamento categorie:", e);
    }
  },

  reloadGraph() {
    this.loadGraph();
  },

  async mounted() {
    this.keyword = this.$route.query.term || "";
    if (!this.keyword) {
      alert("Nessuna keyword specificata");
      this.$router.push("/");
      return;
    }
    await this.loadGraph()
    await this.fetchCategories();
  },

  beforeUnmount() {
    if (this.clickTimer) clearTimeout(this.clickTimer);
    if (this.network) this.network.destroy();
  },

  methods: {
    // ===== UTILITY =====
    cleanNodeId(nodeId) { return String(nodeId).replace(/^user_/, ""); },
    
    getNodeExploredDepth(nodeId) {
      return this.exploredNodesDepth[this.cleanNodeId(nodeId)] || 0;
    },
    
    isNodeExplored(nodeId) {
      return this.getNodeExploredDepth(nodeId) > 0;
    },

    normalizeEdgeId(fromId, toId) {
      const from = Number(this.cleanNodeId(fromId));
      const to = Number(this.cleanNodeId(toId));
      return `edge_${Math.min(from, to)}_${Math.max(from, to)}`;
    },

    getConnectedNodeIds(nodeId) {
      if (!this.edgesDS) return [];
      const connectedIds = new Set();
      for (const edge of this.edgesDS.get()) {
        if (edge.from === nodeId) connectedIds.add(edge.to);
        else if (edge.to === nodeId) connectedIds.add(edge.from);
      }
      return Array.from(connectedIds);
    },

    showToast(msg, time = 2500) { 
      this.toast = msg; 
      setTimeout(() => (this.toast = ""), time); 
    },

    // ===== TENDINE ESPANDIBILI =====
    toggleSentExpanded() { this.sentExpanded = !this.sentExpanded; },
    toggleReceivedExpanded() { this.receivedExpanded = !this.receivedExpanded; },
    isUserExpanded(direction, odId) { return this.expandedUsers.has(`${direction}-${odId}`); },
    
    async toggleUserReplies(direction, item) {
      const key = `${direction}-${item.id}`;
      if (this.expandedUsers.has(key)) {
        this.expandedUsers.delete(key);
        this.expandedUsers = new Set(this.expandedUsers);
      } else {
        this.expandedUsers.add(key);
        this.expandedUsers = new Set(this.expandedUsers);
        if (!this.userRepliesCache[key]) {
          await this.loadUserReplies(direction, item);
        }
      }
    },

    async loadUserReplies(direction, item) {
      const key = `${direction}-${item.id}`;
      this.loadingUserReplies = key;
      try {
        const currentUserId = this.cleanNodeId(this.selectedNode.id);
        let fromId = direction === 'sent' ? currentUserId : item.id;
        let toId = direction === 'sent' ? item.id : currentUserId;
        
        // ✅ Usa mode=keyword per filtrare solo reply con keyword
        const res = await fetch(`http://127.0.0.1:5000/api/reply_utente/${fromId}?keyword=${encodeURIComponent(this.keyword)}&mode=keyword`);
        if (res.ok) {
          const payload = await res.json();
          const rows = Array.isArray(payload) ? payload : (payload.data || []);
          const filtered = rows.filter(r => String(r.reply_to_user_id) === String(toId));
          filtered.sort((a, b) => new Date(b.data_invio) - new Date(a.data_invio));
          this.userRepliesCache[key] = filtered;
        }
      } catch (err) {
        console.error('Errore caricamento reply utente:', err);
        this.userRepliesCache[key] = [];
      } finally {
        this.loadingUserReplies = null;
      }
    },

    formatDate(dateStr) {
      if (!dateStr) return '';
      return new Date(dateStr).toLocaleDateString('it-IT', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
    },

    // ===== TELEGRAM =====
    isPublicChat(m) { return !!(m.chat_username || m.username_chat); },
    
    getTelegramLink(m) {
      const username = m.chat_username || m.username_chat;
      if (username) return `https://t.me/${username}/${m.id_messaggio}`;
      let chatId = (m.id_chat || m.chat_id || "").toString();
      if (chatId.startsWith("-100")) chatId = chatId.substring(4);
      else if (chatId.startsWith("-")) chatId = chatId.substring(1);
      return `https://t.me/c/${chatId}/${m.id_messaggio}`;
    },

    gestisciClickTelegram(m) {
      const link = this.getTelegramLink(m);
      const nomeChat = m.nome_chat || m.provenienza || m.nome_chat_tradotto || "questo gruppo";
      if (this.isPublicChat(m)) { window.open(link, '_blank'); return; }
      if (window.confirm(`🔒 GRUPPO PRIVATO: "${nomeChat}"\n\nQuesto messaggio è in una chat privata.\n\n• SEI GIÀ MEMBRO? Premi OK.\n• NON SEI MEMBRO? Premi Annulla.`)) {
        window.open(link, '_blank');
      }
    },

    // ===== KEYWORD HIGHLIGHT =====
    highlightKeyword(text) {
      if (!text) return "";
      const kw = this.keyword.toLowerCase();
      const escapedKw = kw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const regex = new RegExp(escapedKw, "gi");
      let safe = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
      return safe.replace(regex, (match) => `<mark class="kw-highlight">${match}</mark>`);
    },

    // ===== CARICA GRAFO =====
    async loadGraph() {
  this.loading = true;
  try {
    // 1. Definiamo l'URL base per la ricerca per keyword
    let url = `http://127.0.0.1:5000/api/graph/keyword?term=${encodeURIComponent(this.keyword)}&maxUsers=50&minCount=1&maxTargets=30`;

    // 2. Aggiungiamo il parametro category solo se è stato selezionato dall'utente
    if (this.selectedCategory) {
      url += `&category=${encodeURIComponent(this.selectedCategory)}`;
    }

    // 3. Eseguiamo la fetch all'URL dinamico
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Errore HTTP ${res.status}`);
    
    const json = await res.json();

    // Aggiornamento delle statistiche del grafo
    this.stats = {
      nodes: json.nodes?.length || 0,
      edges: json.keyword_edges?.length || 0,
      keyword_edges: json.keyword_edges?.length || 0,
    };

    this.keywordStats = json.keyword_stats || {};
    this.exploredNodesDepth = {};

    // Mappatura dei nodi con i colori relativi alla presenza della keyword
    const nodes = (json.nodes || []).map((n) => ({
      ...n,
      color: n.hasKeyword
        ? { background: "#facc15", border: "#d97706", highlight: { background: "#fde047", border: "#d97706" }, hover: { background: "#fde047", border: "#d97706" } }
        : { background: "#2563eb", border: "#1e40af", highlight: { background: "#3b82f6", border: "#1e40af" }, hover: { background: "#3b82f6", border: "#1e40af" } },
    }));

    // Inizializzazione dei DataSet per la visualizzazione
    this.nodesDS = new DataSet(nodes);
    this.edgesDS = new DataSet(json.keyword_edges || []);
    
    this.renderGraph();
  } catch (error) {
    console.error("Errore caricamento grafo:", error);
    alert("Errore nel caricamento del grafo.");
  } finally {
    this.loading = false;
  }

},

    renderGraph() {
      if (this.network) this.network.destroy();

      this.network = new Network(
        this.$refs.network,
        { nodes: this.nodesDS, edges: this.edgesDS },
        {
          nodes: { shape: "dot", size: 22, font: { size: 14, color: "#333" } },
          edges: {
            arrows: { to: { enabled: true, scaleFactor: 0.5 } },
            smooth: { type: "dynamic" },
            color: { color: "#ff0000", highlight: "#e63946" },
            width: 2,
            font: { size: 12, align: "middle" }
          },
          physics: {
            solver: "forceAtlas2Based",
            forceAtlas2Based: { gravitationalConstant: -60, springLength: 140, avoidOverlap: 0.5 },
            stabilization: { iterations: 200, updateInterval: 25 }
          },
          interaction: { hover: true, tooltipDelay: 200 }
        }
      );

      this.network.on("click", this.onClick);
      this.network.on("doubleClick", this.onDoubleClick);
      this.network.on("stabilizationIterationsDone", () => {
        this.network.setOptions({ physics: false });
      });
    },

    // ===== CLICK =====
    async onClick(params) {
      clearTimeout(this.clickTimer);
      this.clickTimer = setTimeout(async () => {
        this.closeDetails();
        if (params.nodes.length) {
          const node = this.nodesDS.get(params.nodes[0]);
          this.selectedNode = node;
          this.selectedNodeId = node.id.replace("user_", "");
          await this.loadNodeDetails();
        } else if (params.edges.length) {
          const edge = this.edgesDS.get(params.edges[0]);
          this.selectedEdge = edge;
          await this.loadEdgeDetails(edge);
        }
      }, 250);
    },

    async onDoubleClick(params) {
      clearTimeout(this.clickTimer);
      if (params.nodes.length === 0) return;
      await this.exploreNodeReplies(params.nodes[0]);
    },

    // ===== ESPLORAZIONE NODO (con profondità) =====
    async exploreFocusNode() {
      const q = this.focusQuery.trim();
      if (!q) return this.showToast("Inserisci un ID o username");
      
      // Cerca il nodo nel grafo
      const nodes = this.nodesDS.get();
      const found = nodes.find(n => {
        const cleanId = this.cleanNodeId(n.id);
        return cleanId === q || n.label?.toLowerCase() === q.toLowerCase();
      });
      
      if (found) {
        await this.exploreNodeReplies(found.id);
        this.network.focus(found.id, { animation: { duration: 500 }, scale: 1.5 });
      } else {
        this.showToast("Nodo non trovato nel grafo keyword");
      }
    },

    async exploreNodeReplies(nodeId) {
      const focusClean = this.cleanNodeId(nodeId);
      const previousDepth = this.exploredNodesDepth[focusClean] || 0;
      
      if (previousDepth >= this.depth) {
        return this.showToast(`Già esplorato con profondità ${previousDepth}. Aumenta il valore.`);
      }
      
      try {
        // ✅ Usa l'endpoint keyword per mantenere il focus sulla keyword
        const res = await fetch(
          `http://127.0.0.1:5000/api/reply_utente/${focusClean}?keyword=${encodeURIComponent(this.keyword)}&mode=keyword`
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const payload = await res.json();
        const replies = Array.isArray(payload) ? payload : (payload.data || []);

        this.exploredNodesDepth[focusClean] = this.depth;
        this.updateNodeAsExplored(nodeId);

        // Aggiungi nuovi nodi trovati nelle reply
        let addedNodes = 0;
        const existingNodeIds = new Set(this.nodesDS.getIds());
        
        for (const r of replies) {
          const targetId = `user_${r.reply_to_user_id}`;
          if (!existingNodeIds.has(targetId) && r.reply_to_user_id) {
            this.nodesDS.add({
              id: targetId,
              label: r.reply_to_nome || r.reply_to_username || String(r.reply_to_user_id),
              hasKeyword: false,
              color: { background: "#2563eb", border: "#1e40af" }
            });
            addedNodes++;
            existingNodeIds.add(targetId);
          }
        }

        this.stats = { ...this.stats, nodes: this.nodesDS.length };
        
        if (addedNodes > 0) {
          this.showToast(`Aggiunti ${addedNodes} nodi collegati con keyword`);
        } else {
          this.showToast("Nessun nuovo nodo trovato");
        }
        
      } catch (err) { 
        console.error("Errore espansione:", err); 
        this.showToast("Errore durante l'espansione"); 
      }
    },

    updateNodeAsExplored(nodeId) {
      const existingNode = this.nodesDS.get(nodeId);
      const cleanId = this.cleanNodeId(nodeId);
      const depth = this.exploredNodesDepth[cleanId] || 0;
      
      if (existingNode) {
        this.nodesDS.update({ 
          id: nodeId, 
          color: { background: "#ffd43b", border: "#fab005" },
          title: existingNode.label + ` (esplorato: ${depth})`
        });
      }
    },

    closeDetails() {
      this.selectedNode = null;
      this.selectedEdge = null;
      this.selectedNodeId = null;
      this.nodeDetails = null;
      this.userChats = [];
      this.keywordMessages = [];
      this.edgeMessages = [];
      this.edgeDirectionStats = null;
      this.nodeReplySummary = null;
      // Reset tendine
      this.sentExpanded = false;
      this.receivedExpanded = false;
      this.expandedUsers = new Set();
      this.userRepliesCache = {};
      this.loadingUserReplies = null;
    },

    // ===== DETTAGLIO NODO =====
    async loadNodeDetails() {
      const id = this.selectedNodeId;
      const loadingId = id;
      this.currentLoadingId = loadingId;
      this.nodeReplySummaryLoading = true;

      // Cache check
      if (this.nodeCache[id]) {
        const cached = this.nodeCache[id];
        this.nodeDetails = cached.nodeDetails;
        this.userChats = cached.userChats;
        this.keywordMessages = cached.keywordMessages;
        this.nodeReplySummary = cached.nodeReplySummary;
        this.nodeReplySummaryLoading = false;
        return;
      }

      try {
        const [uRes, relRes, msgRes] = await Promise.all([
          fetch(`http://127.0.0.1:5000/api/utente/${id}`),
          fetch(`http://127.0.0.1:5000/api/reply_utente/${id}?keyword=${encodeURIComponent(this.keyword)}&mode=keyword`),
          fetch(`http://127.0.0.1:5000/api/cerca_messaggi?id_autore=${id}&q=${encodeURIComponent(this.keyword)}`)
        ]);

        if (this.currentLoadingId !== loadingId) return;
        if (!uRes.ok || !relRes.ok || !msgRes.ok) throw new Error("Errore nel caricamento");

        const [uj, relj, msgj] = await Promise.all([uRes.json(), relRes.json(), msgRes.json()]);
        if (this.currentLoadingId !== loadingId) return;

        this.nodeDetails = uj.user;
        this.userChats = uj.chats || [];
        this.keywordMessages = (msgj.data || []).filter(m => !m.reply_to_msg_id);

        // ✅ Costruisci riepilogo reply CON KEYWORD
        const keywordReplies = Array.isArray(relj) ? relj : (relj.data || []);
        await this.buildNodeReplySummary(id, keywordReplies);

        // Cache
        this.nodeCache[id] = {
          nodeDetails: this.nodeDetails,
          userChats: this.userChats,
          keywordMessages: this.keywordMessages,
          nodeReplySummary: this.nodeReplySummary
        };

      } catch (error) {
        console.error("Errore caricamento dettagli nodo:", error);
      } finally {
        this.nodeReplySummaryLoading = false;
      }
    },

    async buildNodeReplySummary(userId, keywordReplies) {
      // Raggruppa reply inviate per destinatario
      const sentMap = new Map();
      for (const r of keywordReplies) {
        const destId = String(r.reply_to_user_id);
        if (!destId || destId === 'null') continue;
        const nome = r.reply_to_nome?.trim() || (r.reply_to_username ? '@' + r.reply_to_username : '') || `Utente ${destId}`;
        if (!sentMap.has(destId)) sentMap.set(destId, { id: destId, nome, count: 0 });
        sentMap.get(destId).count++;
      }

      // Recupera reply ricevute (da vicini nel grafo)
      const receivedMap = new Map();
      const connectedNodeIds = this.getConnectedNodeIds(`user_${userId}`);
      
      for (const neighborId of connectedNodeIds) {
        const neighborCleanId = this.cleanNodeId(neighborId);
        if (neighborCleanId === userId) continue;
        
        try {
          const resNeighbor = await fetch(`http://127.0.0.1:5000/api/reply_utente/${neighborCleanId}?keyword=${encodeURIComponent(this.keyword)}&mode=keyword`);
          if (resNeighbor.ok) {
            const payload = await resNeighbor.json();
            const neighborReplies = Array.isArray(payload) ? payload : (payload.data || []);
            const repliesToUser = neighborReplies.filter(r => String(r.reply_to_user_id) === userId);
            
            if (repliesToUser.length > 0) {
              const first = repliesToUser[0];
              const nome = first.autore_nome?.trim() || (first.autore_username ? '@' + first.autore_username : '') || `Utente ${neighborCleanId}`;
              receivedMap.set(neighborCleanId, { id: neighborCleanId, nome, count: repliesToUser.length });
            }
          }
        } catch (e) { console.warn(`Errore fetch reply da ${neighborCleanId}:`, e); }
      }

      const sentList = Array.from(sentMap.values()).sort((a, b) => b.count - a.count);
      const receivedList = Array.from(receivedMap.values()).sort((a, b) => b.count - a.count);

      this.nodeReplySummary = {
        sent: sentList,
        received: receivedList,
        totalSent: sentList.reduce((sum, x) => sum + x.count, 0),
        totalReceived: receivedList.reduce((sum, x) => sum + x.count, 0)
      };
    },

    // ===== DETTAGLIO ARCO =====
    async loadEdgeDetails(edge) {
      const from = edge.from.replace("user_", "");
      const to = edge.to.replace("user_", "");
      this.edgeDirectionStats = null;

      try {
        // ✅ Fetch bidirezionale con keyword
        let messagesAtoB = [], messagesBtoA = [];
        
        try {
          const res1 = await fetch(`http://127.0.0.1:5000/api/reply_utente/${from}?keyword=${encodeURIComponent(this.keyword)}&mode=keyword`);
          if (res1.ok) {
            const payload = await res1.json();
            const rows = Array.isArray(payload) ? payload : (payload.data || []);
            messagesAtoB = rows.filter(r => String(r.reply_to_user_id) === to);
          }
        } catch (e) { console.warn("Errore fetch A→B:", e); }

        try {
          const res2 = await fetch(`http://127.0.0.1:5000/api/reply_utente/${to}?keyword=${encodeURIComponent(this.keyword)}&mode=keyword`);
          if (res2.ok) {
            const payload = await res2.json();
            const rows = Array.isArray(payload) ? payload : (payload.data || []);
            messagesBtoA = rows.filter(r => String(r.reply_to_user_id) === from);
          }
        } catch (e) { console.warn("Errore fetch B→A:", e); }

        // ✅ Statistiche bidirezionali
        this.edgeDirectionStats = {
          aToB: messagesAtoB.length,
          bToA: messagesBtoA.length,
          total: messagesAtoB.length + messagesBtoA.length
        };

        // Combina e ordina
        const allMessages = [...messagesAtoB, ...messagesBtoA].sort((a, b) => 
          new Date(b.data_invio) - new Date(a.data_invio)
        );
        this.edgeMessages = allMessages;

        // Calcola totale keyword
        edge.keyword_total = allMessages.reduce(
          (acc, m) => acc + (m.keyword_count_reply || 0) + (m.keyword_count_original || 0), 0
        );
        
        // Nomi
        if (allMessages.length > 0) {
          const firstAtoB = messagesAtoB[0];
          const firstBtoA = messagesBtoA[0];
          edge.fromNome = firstAtoB?.autore_nome || firstBtoA?.reply_to_nome || from;
          edge.toNome = firstAtoB?.reply_to_nome || firstBtoA?.autore_nome || to;
        }

      } catch (error) {
        console.error("Errore caricamento dettagli arco:", error);
      }
    },
  },
};
</script>

<style scoped>
.graph-filtrato-page { padding: 1rem 1.5rem; position: relative; }
.page-title { font-size: 1.7rem; font-weight: 700; margin-bottom: 1rem; }
.kw { color: #1d4ed8; }

/* STATS */
.stats-box { display: flex; gap: 1rem; margin-bottom: 0.8rem; }
.stat-item { background: #eef1f6; padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.9rem; }
.keyword-item { background: #fde047; color: #854d0e; font-weight: bold; }

/* LEGENDA */
.legenda-box { background: #fff; padding: 12px 18px; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); width: fit-content; margin-bottom: 15px; }
.legend-item { display: flex; align-items: center; margin-bottom: 5px; font-size: 0.9rem; }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; border: 1px solid #333; }
.legend-line { display: inline-block; width: 20px; height: 3px; margin-right: 8px; }
.legend-dot.keyword-dot { background: #facc15; border-color: #d97706; }
.legend-dot.normal-dot { background: #2563eb; border-color: #1e40af; }
.legend-line.keyword-line { background-color: #ff0000; opacity: 0.8; }

/* SEARCH BAR */
.search-bar { display: flex; gap: 0.6rem; margin-bottom: 1rem; flex-wrap: wrap; }
.search-input { flex: 2; min-width: 200px; padding: 0.5rem 0.8rem; border: 1px solid #ccc; border-radius: 6px; font-size: 0.95rem; }
.depth-input { width: 70px; padding: 0.4rem; border: 1px solid #ccc; border-radius: 6px; text-align: center; }
.depth-box { display: flex; flex-direction: column; align-items: center; }
.depth-label { font-size: 0.7rem; color: #555; }
.search-btn { background: #3558ff; color: #fff; border: none; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; font-weight: 600; }
.search-btn:hover { background: #2f4dd7; }

/* LOADER */
.loading-overlay { position: fixed; inset: 0; background: rgba(255,255,255,0.9); display: flex; flex-direction: column; justify-content: center; align-items: center; z-index: 1000; }
.spinner { border: 4px solid #f3f3f3; border-top: 4px solid #1d4ed8; border-radius: 50%; width: 50px; height: 50px; animation: spin 1s linear infinite; }
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

/* GRAPH */
.graph-container { height: 70vh; border-radius: 10px; background: white; box-shadow: 0 2px 6px rgba(0,0,0,0.08); }

/* MODAL */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.45); display: flex; justify-content: center; align-items: center; z-index: 999; }
.modal { background: white; padding: 1.5rem; border-radius: 12px; width: 520px; max-width: 90vw; max-height: 85vh; overflow-y: auto; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }
.modal h3 { margin-top: 0; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.modal h4 { margin-top: 1.2rem; margin-bottom: 0.5rem; color: #374151; font-size: 1.1rem; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.3rem; }
.modal p { margin: 0.5rem 0; line-height: 1.5; }

/* KEYWORD HIGHLIGHT BOX */
.keyword-highlight-box { background: #fef3c7; padding: 8px 12px; border-left: 4px solid #f59e0b; border-radius: 6px; margin: 0.8rem 0; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.kw-highlight { background: #ffd54f; padding: 2px 4px; border-radius: 4px; font-weight: bold; }

/* BADGE */
.badge { padding: 3px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
.badge.Utente { background: #16a34a; color: white; }
.badge.keyword { background: #fde047; color: #854d0e; }
.badge.explored { background: #fab005; color: white; }

/* LISTS */
.reply-list { list-style: none; margin: 0.5rem 0; padding: 0; }
.reply-list li { border-bottom: 1px solid #eee; padding: 0.6rem 0; }
.reply-list li:last-child { border-bottom: none; }
.msg-meta-row { display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.3rem; font-size: 0.9rem; }
.msg-text { background: #f5f5f5; padding: 0.4rem 0.6rem; border-radius: 4px; border-left: 3px solid #3558ff; margin: 0.3rem 0; display: block; }

/* EDGE VISUAL */
.edge-summary-visual { display: flex; align-items: center; justify-content: space-between; padding: 1rem; background: #f8f9fa; border-radius: 8px; margin-bottom: 1rem; gap: 0.5rem; }
.edge-user { display: flex; flex-direction: column; align-items: center; gap: 0.4rem; flex: 1; }
.edge-user-name { font-size: 0.85rem; font-weight: 600; color: #1d3b70; text-align: center; }
.edge-arrow-container { display: flex; flex-direction: column; align-items: center; gap: 0.3rem; }
.edge-total { font-size: 1.5rem; font-weight: 700; color: #3558ff; background: #eef4ff; padding: 0.3rem 0.8rem; border-radius: 20px; }
.edge-direction { font-size: 0.8rem; }
.direction-count { padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: 600; }
.direction-count.out { background: #fff5f5; color: #e63946; }
.direction-count.in { background: #f0fff4; color: #2ca02c; }
.avatar-placeholder { width: 48px; height: 48px; border-radius: 50%; background: #e9ecef; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; }

/* REPLY SUMMARY (come Grafo.vue) */
.reply-summary-section { margin: 1rem 0; padding: 0.8rem; background: #f8f9fa; border-radius: 8px; border: 1px solid #e9ecef; }
.reply-summary-section h4 { margin: 0 0 0.8rem 0; font-size: 1rem; color: #1d3b70; border: none; padding: 0; }
.reply-direction-box { margin: 0.6rem 0; padding: 0.6rem; border-radius: 6px; }
.sent-box { background: #fff5f5; border-left: 4px solid #e63946; }
.received-box { background: #f0fff4; border-left: 4px solid #2ca02c; }
.direction-label { margin: 0 0 0.4rem 0; font-size: 0.9rem; display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.arrow-icon { font-size: 1.1rem; font-weight: bold; }
.sent-box .arrow-icon { color: #e63946; }
.received-box .arrow-icon { color: #2ca02c; }
.total-badge { background: #e9ecef; padding: 0.1rem 0.5rem; border-radius: 10px; font-size: 0.8rem; color: #495057; margin-left: auto; }
.expand-icon { font-size: 0.7rem; color: #666; margin-left: 8px; }
.interaction-list { list-style: none; padding: 0; margin: 0; }
.interaction-list li { display: flex; justify-content: space-between; align-items: center; padding: 0.3rem 0.5rem; margin: 0.2rem 0; background: #fff; border-radius: 4px; font-size: 0.85rem; border: none; }
.interaction-name { color: #1d3b70; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 180px; }
.interaction-count { color: #fff; font-size: 0.75rem; background: #6c757d; padding: 0.1rem 0.5rem; border-radius: 10px; min-width: 24px; text-align: center; }
.interaction-item-clickable { cursor: pointer; transition: background 0.2s; }
.interaction-item-clickable:hover { background: #e9ecef !important; }
.expand-arrow { font-size: 0.65rem; color: #888; margin-left: 8px; }
.reply-detail-box { background: #fff !important; border: 1px solid #dee2e6 !important; border-radius: 6px !important; margin: 4px 0 8px 0 !important; padding: 8px !important; display: block !important; }
.reply-messages-list { list-style: none; padding: 0; margin: 0; }
.reply-messages-list li { padding: 6px 0; border-bottom: 1px dashed #eee; background: transparent !important; display: block !important; }
.reply-messages-list li:last-child { border-bottom: none; }
.mini-msg { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 0.75rem; }
.mini-date { color: #666; font-style: italic; }
.mini-chat { color: #1d3b70; font-weight: 500; }
.mini-text { margin: 4px 0 0 0; font-size: 0.8rem; color: #444; line-height: 1.4; background: #f8f9fa; padding: 4px 8px; border-radius: 4px; border-left: 2px solid #f59e0b; }
.more-messages { font-style: italic; color: #888; font-size: 0.75rem; text-align: center; padding: 4px !important; }
.more-items-link { font-style: italic; color: #3558ff; font-size: 0.8rem; cursor: pointer; padding: 4px 8px; margin-top: 4px; }
.more-items-link:hover { text-decoration: underline; }
.expanded-list { margin-top: 4px; border-top: 1px dashed #ddd; padding-top: 4px; }
.reply-balance { margin-top: 0.8rem; padding: 0.5rem; text-align: center; border-radius: 6px; font-size: 0.9rem; font-weight: 600; }
.balance-positive { background: #fff3cd; color: #856404; }
.balance-negative { background: #d4edda; color: #155724; }
.balance-neutral { background: #e2e3e5; color: #383d41; }
.loading-summary { text-align: center; padding: 1rem; color: #666; font-style: italic; }
.loading-mini { text-align: center; padding: 8px; color: #666; font-size: 0.8rem; }
.more-items { font-style: italic; color: #888; font-size: 0.85rem; }

/* BUTTONS */
.btn-close { margin-top: 1.5rem; background: #e63946; color: white; padding: 0.6rem 1rem; border-radius: 8px; width: 100%; border: none; cursor: pointer; font-weight: bold; }
.btn-close:hover { background: #d62839; }
.username-link { color: #3558ff; text-decoration: none; font-weight: 600; display: inline-block; margin-top: 0.8rem; margin-right: 1rem; }

/* TELEGRAM */
.tg-link { display: inline-flex; align-items: center; gap: 0.2rem; font-size: 0.75rem; font-weight: 600; color: #0088cc; background-color: #e3f2fd; padding: 0.15rem 0.4rem; border-radius: 5px; text-decoration: none; }
.tg-link:hover { background-color: #0088cc; color: white; }
.tg-link.tg-private { color: #b45309; background-color: #fffbeb; }
.tg-link.tg-private:hover { background-color: #f59e0b; color: white; }
.tg-link-mini { font-size: 0.7rem; padding: 1px 4px; background: #e3f2fd; border-radius: 3px; text-decoration: none; }
.tg-link-mini:hover { background: #0088cc; color: white; }

/* KEYWORD REF */
.keyword-ref { background: #f0f7ff; padding: 8px 12px; border-left: 4px solid #1d4ed8; border-radius: 6px; margin-bottom: 1rem; }

/* TOAST */
.toast { position: fixed; bottom: 1.5rem; right: 1.5rem; background: #333; color: #fff; padding: 0.7rem 1.2rem; border-radius: 6px; font-size: 0.9rem; z-index: 3000; }

/* SCROLLBAR */
.modal::-webkit-scrollbar { width: 8px; }
.modal::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 10px; }
.modal::-webkit-scrollbar-thumb { background: #888; border-radius: 10px; }
.modal::-webkit-scrollbar-thumb:hover { background: #555; }

@media (max-width: 768px) {
  .edge-summary-visual { flex-direction: column; gap: 1rem; }
}

.category-select {
  padding: 0.5rem 0.8rem;
  border: 1px solid #ccc;
  border-radius: 6px;
  background: white;
  font-size: 0.95rem;
  max-width: 200px;
  cursor: pointer;
}

.category-select:focus {
  outline: none;
  border-color: #3558ff;
}
</style>