<template>
  <div class="graph-page">
    <h1 class="page-title">Visualizzazione modello a grafo</h1>
    <p class="page-description">
      Questa dashboard mostra un estratto casuale delle interazioni più rilevanti tra utenti su Telegram,
      calcolate in base al numero di <strong>reply</strong> scambiati (peso).
    </p>

    <div v-if="stats" class="stats-box">
      <div class="stat-item"><strong>{{ stats.nodes }}</strong> Nodi</div>
      <div class="stat-item"><strong>{{ stats.edges }}</strong> Relazioni (archi)</div>
    </div>

    <div class="search-bar">
      <select v-model="selectedCategory" @change="reloadGraph" class="category-select">
      <option value=""> Tutte le categorie</option>
      <option v-for="cat in categories" :key="cat.categoria_chat" :value="cat.categoria_chat">
        {{ cat.categoria_chat }} ({{ cat.totale }})
      </option>
      </select>

      <input
        v-model="query"
        class="search-input"
        type="text"
        placeholder="🔎 Inserisci ID o username di un utente o di una chat per esplorare il grafo"
        @keyup.enter="searchUserReplies"
      />

      <div class="depth-box">
        <input
          v-model.number="depth"
          class="depth-input"
          type="number"
          min="1"
          placeholder="Profondità"
        />
        <small class="depth-label">Numero di nodi da esplorare</small>
      </div>

      <button @click="searchUserReplies" class="search-btn">Cerca</button>
    </div>

    <!-- ✅ Banner Chat/Canale migliorato -->
    <div v-if="chatContext" class="chat-banner" :class="{ 'channel-banner': chatContext.is_channel }">
      <span class="chat-icon">{{ chatContext.is_channel ? '📢' : '💬' }}</span>
      <div class="chat-banner-content">
        <span v-if="chatContext.is_channel">
          Stai visualizzando i <strong>top {{ depth }}</strong> commentatori del canale
        </span>
        <span v-else>
          Stai visualizzando i <strong>top {{ depth }}</strong> utenti della chat
        </span>
        <strong>{{ chatContext.nome_chat_tradotto || chatContext.nome_chat }}</strong>
        <span class="chat-cat">({{ chatContext.categoria_chat || 'Non classificata' }})</span>
      </div>
    </div>

    <!-- ✅ Messaggio per canali senza interazioni -->
    <div v-if="channelMessage" class="channel-notice">
      <span class="notice-icon">📢</span>
      <p>{{ channelMessage }}</p>
    </div>

    <div class="graph-layout">
      <div ref="graphContainer" class="graph-container"></div>

      <div class="legend">
        <h3>Legenda</h3>
        <ul>
          <li><span class="legend-color" style="background:#2ca02c"></span> Utente</li>
          <li><span class="legend-color" style="background:#ff6b6b"></span> Nodo Focus</li>
          <li><span class="legend-color" style="background:#ffd43b"></span> Già esplorato</li>
        </ul>
        <p class="legend-note">
          <strong>Peso</strong>: numero di reply scambiati (bidirezionale).<br />
          Più alto è il peso, maggiore l'arco è marcato (blu scuro e più spesso).<br />
          <strong>Doppio click</strong> su un nodo per espanderlo.
        </p>
      </div>
    </div>

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
        <p class="mono"><strong>ID:</strong> {{ selectedNode.id.replace('user_', '') }}</p>
        <p><strong>Username:</strong> {{ nodeDetails?.username && nodeDetails.username.trim() !== '' ? nodeDetails.username : 'sconosciuto' }}</p>

        <div v-if="nodeDetails">
          <p><strong>Nome:</strong> {{ nodeDetails.nome }}</p>
          <p><strong>Ultima attività:</strong> {{ nodeDetails.ultima_attivita }}</p>
          <p><strong>Messaggi totali:</strong> {{ nodeDetails.messaggi_totali }}</p>
        </div>

        <!-- Riepilogo Interazioni Reply con TENDINE ESPANDIBILI -->
        <div v-if="nodeReplySummary && (nodeReplySummary.sent.length || nodeReplySummary.received.length)" class="reply-summary-section">
          <h4>📊 Riepilogo Interazioni Reply</h4>
          
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
                    <p class="mini-text">{{ truncateText(msg.reply_text || msg.testo, 100) }}</p>
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
              
              <template v-for="(item, idx) in nodeReplySummary.sent.slice(5)" :key="'sent-exp-detail-'+idx">
                <div v-if="isUserExpanded('sent', item.id)" class="reply-detail-box">
                  <div v-if="loadingUserReplies === 'sent-'+item.id" class="loading-mini">⏳ Caricamento...</div>
                  <ul v-else-if="userRepliesCache['sent-'+item.id]" class="reply-messages-list">
                    <li v-for="(msg, mIdx) in userRepliesCache['sent-'+item.id].slice(0, 3)" :key="'msg-exp-'+mIdx">
                      <div class="mini-msg">
                        <span class="mini-date">{{ formatDate(msg.data_invio) }}</span>
                        <span class="mini-chat">{{ msg.nome_chat_tradotto || msg.nome_chat }}</span>
                      </div>
                      <p class="mini-text">{{ truncateText(msg.reply_text || msg.testo, 100) }}</p>
                    </li>
                  </ul>
                </div>
              </template>
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
                    <p class="mini-text">{{ truncateText(msg.reply_text || msg.testo, 100) }}</p>
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
              
              <template v-for="(item, idx) in nodeReplySummary.received.slice(5)" :key="'recv-exp-detail-'+idx">
                <div v-if="isUserExpanded('received', item.id)" class="reply-detail-box">
                  <div v-if="loadingUserReplies === 'received-'+item.id" class="loading-mini">⏳ Caricamento...</div>
                  <ul v-else-if="userRepliesCache['received-'+item.id]" class="reply-messages-list">
                    <li v-for="(msg, mIdx) in userRepliesCache['received-'+item.id].slice(0, 3)" :key="'msg-recv-exp-'+mIdx">
                      <div class="mini-msg">
                        <span class="mini-date">{{ formatDate(msg.data_invio) }}</span>
                        <span class="mini-chat">{{ msg.nome_chat_tradotto || msg.nome_chat }}</span>
                      </div>
                      <p class="mini-text">{{ truncateText(msg.reply_text || msg.testo, 100) }}</p>
                    </li>
                  </ul>
                </div>
              </template>
              <p class="more-items-link" @click="toggleReceivedExpanded">▲ Nascondi</p>
            </template>
          </div>

          <div class="reply-balance" :class="balanceClass">{{ balanceText }}</div>
        </div>

        <div v-if="nodeReplySummaryLoading" class="loading-summary">⏳ Caricamento interazioni...</div>

        <div v-if="userChats && userChats.length">
          <h4>Distribuzione messaggi per chat</h4>
          <ul class="reply-list">
            <li v-for="(c, idx) in userChats.slice(0, 5)" :key="'chat-'+idx">
              <strong>{{ c.nome_chat_tradotto || c.nome_chat }}</strong> — {{ c.messaggi_utente }} messaggi
            </li>
            <li v-if="userChats.length > 5" class="more-items">... e altre {{ userChats.length - 5 }} chat</li>
          </ul>
        </div>

        <div v-if="userMessages.length">
          <h4>Ultimi messaggi</h4>
          <ul class="reply-list">
            <li v-for="(m, idx) in userMessages.slice(0,3)" :key="'um-'+idx">
              <p>
                <em>{{ m.data_invio }}</em> — <strong>{{ m.nome_chat_tradotto || m.nome_chat }}</strong>
                <a href="#" class="tg-link" :class="{ 'tg-private': !isPublicChat(m) }"
                   @click.stop.prevent="gestisciClickTelegram(m)">
                  <span v-if="isPublicChat(m)">✈️</span><span v-else>🔒</span>
                </a>
              </p>
              <p>{{ m.testo_tradotto || m.testo }}</p>
            </li>
          </ul>
        </div>

        <router-link :to="{ name: 'UtenteDettaglio', params: { userId: selectedNode.id.replace('user_', '') } }" class="username-link mt-8">
          Vai al dettaglio utente
        </router-link>
        <button class="btn-close" @click="closeDetails">Chiudi</button>
      </div>
    </div>

    <!-- MODAL DETTAGLIO ARCO -->
    <div v-if="selectedEdge" class="modal-overlay" @click.self="closeDetails">
      <div class="modal">
        <h3>Dettagli reply (bidirezionale)</h3>
        
        <div class="edge-summary-visual">
          <div class="edge-user">
            <img v-if="selectedEdge.avatar_from" :src="selectedEdge.avatar_from" class="avatar-md" />
            <div v-else class="avatar-placeholder">👤</div>
            <span class="edge-user-name">{{ selectedEdge.fromNome?.trim() || selectedEdge.fromUser || selectedEdge.from?.replace('user_', '') }}</span>
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
            <img v-if="selectedEdge.avatar_to" :src="selectedEdge.avatar_to" class="avatar-md" />
            <div v-else class="avatar-placeholder">👤</div>
            <span class="edge-user-name">{{ selectedEdge.toNome?.trim() || selectedEdge.toUser || selectedEdge.to?.replace('user_', '') }}</span>
          </div>
        </div>

        <div v-if="edgeMessages.length">
          <h4>Ultimi messaggi di reply</h4>
          <ul class="reply-list">
            <li v-for="(m, idx) in edgeMessages.slice(0,5)" :key="'em-'+idx">
              <div class="msg-header">
                <img v-if="m.avatar_from" :src="m.avatar_from" class="avatar-sm" />
                <div>
                  <p>
                    <strong>{{ m.autore_nome?.trim() || (m.autore_username ? '@' + m.autore_username : '') || m.autore_id }}</strong>
                    → <span class="reply-to-name">{{ m.reply_to_nome?.trim() || (m.reply_to_username ? '@' + m.reply_to_username : '') || m.reply_to_user_id }}</span>
                  </p>
                  <p class="msg-meta">
                    <em>{{ m.data_invio }}</em> — <strong>{{ m.nome_chat_tradotto || m.nome_chat }}</strong>
                    <a href="#" class="tg-link" :class="{ 'tg-private': !isPublicChat(m) }" @click.stop.prevent="gestisciClickTelegram(m)">
                      <span v-if="isPublicChat(m)">✈️</span><span v-else>🔒</span>
                    </a>
                  </p>
                </div>
              </div>
              <p class="msg-text">{{ m.testo_tradotto || m.reply_text || m.testo }}</p>
            </li>
          </ul>
        </div>

        <div v-if="edgeMessagesLoading" class="loading-summary">⏳ Caricamento messaggi...</div>
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
  name: "Grafo",
  data() {
    return {
      stats: null,
      query: "",
      depth: 5,
      toast: "",
      network: null,
      nodesDS: null,
      edgesDS: null,
      selectedNode: null,
      selectedEdge: null,
      nodeDetails: null,
      userMessages: [],
      userChats: [],
      edgeMessages: [],
      lastJson: null,
      clickTimer: null,
      chatContext: null,
      initialFocusId: null,
      nodeReplySummary: null,
      nodeReplySummaryLoading: false,
      edgeDirectionStats: null,
      edgeMessagesLoading: false,
      
      // ✅ Traccia profondità per ogni nodo
      exploredNodesDepth: {},
      
      // ✅ Messaggio per canali senza interazioni
      channelMessage: null,
      
      // Tendine espandibili
      sentExpanded: false,
      receivedExpanded: false,
      expandedUsers: new Set(),
      userRepliesCache: {},
      loadingUserReplies: null,
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

  beforeUnmount() {
    if (this.clickTimer) { clearTimeout(this.clickTimer); this.clickTimer = null; }
    if (this.network) { this.network.destroy(); this.network = null; }
    if (this.nodesDS) { this.nodesDS.clear(); this.nodesDS = null; }
    if (this.edgesDS) { this.edgesDS.clear(); this.edgesDS = null; }
  },

  methods: {
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

    // TENDINE ESPANDIBILI
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
        
        const res = await fetch(`http://127.0.0.1:5000/api/reply_utente/${fromId}`);
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
    truncateText(text, maxLen = 100) {
      if (!text) return '';
      return text.length <= maxLen ? text : text.substring(0, maxLen) + '...';
    },

    // TELEGRAM
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

    async translateText(text) {
      if (!text) return "";
      try {
        const res = await fetch("http://127.0.0.1:5000/api/traduci", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q: text }) });
        const data = await res.json();
        return data.translatedText || text;
      } catch { return text; }
    },

    async fetchNodeDetails(node) {
      this.nodeDetails = null;
      this.userMessages = [];
      this.userChats = [];
      this.nodeReplySummary = null;
      this.nodeReplySummaryLoading = true;
      try {
        if (node.id.startsWith("user_")) {
          const id = this.cleanNodeId(node.id);
          const res = await fetch(`http://127.0.0.1:5000/api/utente/${id}`);
          if (res.ok) { const data = await res.json(); this.nodeDetails = data.user || null; this.userChats = data.chats || []; }
          const mres = await fetch(`http://127.0.0.1:5000/api/messaggi_utente/${id}`);
          if (mres.ok) {
            const data = await mres.json();
            this.userMessages = await Promise.all((data.data || []).slice(0, 3).map(async m => { m.testo_tradotto = await this.translateText(m.testo); return m; }));
          }
          await this.fetchNodeReplySummary(id);
        }
      } catch (err) { console.error("Errore fetch dettagli nodo:", err); this.nodeDetails = { errore: "Impossibile caricare" }; }
      finally { this.nodeReplySummaryLoading = false; }
    },

    async fetchNodeReplySummary(userId) {
      try {
        const resSent = await fetch(`http://127.0.0.1:5000/api/reply_utente/${userId}`);
        let sentReplies = [];
        if (resSent.ok) { const payload = await resSent.json(); sentReplies = Array.isArray(payload) ? payload : (payload.data || []); }
        const sentMap = new Map();
        for (const r of sentReplies) {
          const destId = String(r.reply_to_user_id);
          if (!destId || destId === 'null') continue;
          const nome = r.reply_to_nome?.trim() || (r.reply_to_username ? '@' + r.reply_to_username : '') || `Utente ${destId}`;
          if (!sentMap.has(destId)) sentMap.set(destId, { id: destId, nome, count: 0 });
          sentMap.get(destId).count++;
        }
        const receivedMap = new Map();
        const connectedNodeIds = this.getConnectedNodeIds(`user_${userId}`);
        for (const neighborId of connectedNodeIds) {
          const neighborCleanId = this.cleanNodeId(neighborId);
          if (neighborCleanId === userId) continue;
          try {
            const resNeighbor = await fetch(`http://127.0.0.1:5000/api/reply_utente/${neighborCleanId}`);
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
          sent: sentList, received: receivedList,
          totalSent: sentList.reduce((sum, x) => sum + x.count, 0),
          totalReceived: receivedList.reduce((sum, x) => sum + x.count, 0)
        };
      } catch (err) { console.error("Errore fetch reply summary:", err); this.nodeReplySummary = null; }
    },
    async fetchCategories() {
  try {
    const res = await fetch("http://127.0.0.1:5000/api/chat_per_categoria");
    if (res.ok) {
      const json = await res.json();
      this.categories = json.data || [];
    }
  } catch (e) {
    console.error("Errore categorie:", e);
  }
},

reloadGraph() {
  this.loadGraph(50);
},

    async fetchEdgeDetails(edge) {
      this.edgeMessages = [];
      this.edgeDirectionStats = null;
      this.edgeMessagesLoading = true;
      try {
        if (!edge?.from || !edge?.to) return;
        const fromId = this.cleanNodeId(edge.from);
        const toId = this.cleanNodeId(edge.to);
        let messagesAtoB = [], messagesBtoA = [];
        try {
          const res1 = await fetch(`http://127.0.0.1:5000/api/reply_utente/${fromId}`);
          if (res1.ok) { const payload = await res1.json(); const rows = Array.isArray(payload) ? payload : (payload.data || []); messagesAtoB = rows.filter(r => String(r.reply_to_user_id) === toId); }
        } catch (e) { console.warn("Errore fetch reply A→B:", e); }
        try {
          const res2 = await fetch(`http://127.0.0.1:5000/api/reply_utente/${toId}`);
          if (res2.ok) { const payload = await res2.json(); const rows = Array.isArray(payload) ? payload : (payload.data || []); messagesBtoA = rows.filter(r => String(r.reply_to_user_id) === fromId); }
        } catch (e) { console.warn("Errore fetch reply B→A:", e); }
        this.edgeDirectionStats = { aToB: messagesAtoB.length, bToA: messagesBtoA.length, total: messagesAtoB.length + messagesBtoA.length };
        const allMessages = [...messagesAtoB, ...messagesBtoA].sort((a, b) => new Date(b.data_invio) - new Date(a.data_invio));
        this.edgeMessages = await Promise.all(allMessages.slice(0, 5).map(async m => { m.testo_tradotto = await this.translateText(m.reply_text || m.testo); return m; }));
        const updatedEdge = { ...edge, value: this.edgeDirectionStats.total };
        try { const resFrom = await fetch(`http://127.0.0.1:5000/api/utente/${fromId}`); if (resFrom.ok) { const d = await resFrom.json(); if (d.user) { updatedEdge.fromNome = d.user.nome; updatedEdge.fromUser = d.user.username; } } } catch {}
        try { const resTo = await fetch(`http://127.0.0.1:5000/api/utente/${toId}`); if (resTo.ok) { const d = await resTo.json(); if (d.user) { updatedEdge.toNome = d.user.nome; updatedEdge.toUser = d.user.username; } } } catch {}
        this.selectedEdge = updatedEdge;
      } catch (err) { console.error("Errore fetch arco:", err); }
      finally { this.edgeMessagesLoading = false; }
    },

    async loadGraph(limit = 300) {
  try {
    // 1. Costruisci l'URL base con il limite
    let url = `http://127.0.0.1:5000/api/graph?limit=${limit}`;

    // 2. Aggiungi il parametro category se selezionato
    if (this.selectedCategory) {
      url += `&category=${encodeURIComponent(this.selectedCategory)}`;
    }

    // 3. Esegui la chiamata fetch all'URL aggiornato
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    const json = await res.json();
    this.lastJson = json;
    this.exploredNodesDepth = {};
    this.initialFocusId = null;
    this.chatContext = null;
    this.channelMessage = null;
    this.stats = { nodes: (json.nodes || []).length, edges: (json.edges || []).length };
    
    const processed = await this.processGraphData(json.nodes || [], json.edges || []);
    this.nodesDS = new DataSet(processed.nodes);
    this.edgesDS = new DataSet(processed.edges);
    this.renderNetwork(this.nodesDS, this.edgesDS);
  } catch (err) { 
    console.error("Errore caricamento grafo:", err); 
    this.showToast("Errore nel caricamento del grafo"); 
  }
},

    getNodeColor(nodeId, isFocus = false) {
      const exploredDepth = this.getNodeExploredDepth(nodeId);
      if (isFocus) return { background: "#ff6b6b", border: "#c92a2a", highlight: { background: "#ff8787", border: "#e03131" }, hover: { background: "#ffa8a8", border: "#e03131" } };
      if (exploredDepth > 0) return { background: "#ffd43b", border: "#fab005", highlight: { background: "#ffe066", border: "#f59f00" }, hover: { background: "#ffec99", border: "#f59f00" } };
      return { background: "#2ca02c", border: "#145214", highlight: { background: "#4CAF50", border: "#1B5E20" }, hover: { background: "#66BB6A", border: "#1B5E20" } };
    },

    async processGraphData(nodes, edges, focusId = null) {
      const weights = edges.map(e => Number(e.value ?? e.peso ?? 1)).filter(n => !isNaN(n));
      const wMin = weights.length ? Math.min(...weights) : 1;
      const wMax = weights.length ? Math.max(...weights) : 1;
      const seen = new Set();
      const processedNodes = (nodes || []).map(n => {
        if (seen.has(n.id)) return null;
        seen.add(n.id);
        const cleanId = this.cleanNodeId(n.id);
        const safeLabel = n.label && n.label.trim() !== "" ? n.label : String(n.id);
        const exploredDepth = this.exploredNodesDepth[cleanId] || 0;
        const isFocus = focusId && cleanId === String(focusId);
        let nodeColor = n.color || this.getNodeColor(n.id, isFocus);
        if (exploredDepth > 0 && !isFocus) nodeColor = this.getNodeColor(n.id, false);
        
        let title = safeLabel;
        if (isFocus) title += " (focus)";
        else if (exploredDepth > 0) title += ` (esplorato: ${exploredDepth})`;
        
        return { ...n, label: safeLabel, font: { color: "#000" }, shape: "dot", scaling: { min: 10, max: 45 }, title, color: nodeColor };
      }).filter(Boolean);
      const nodeMap = {};
      processedNodes.forEach(n => (nodeMap[n.id] = true));
      const seenEdges = new Set();
      const processedEdges = (edges || []).map((e) => {
        const value = Number(e.value ?? e.peso ?? 1);
        const normalizedId = this.normalizeEdgeId(e.from, e.to);
        if (seenEdges.has(normalizedId)) return null;
        seenEdges.add(normalizedId);
        const color = this.blueByWeight(value, wMin, wMax);
        return { ...e, id: normalizedId, value, width: Math.max(1, Math.log2(value + 1)), color: { color, highlight: color, hover: color }, label: value ? `${value}` : "", font: { size: 9, align: "horizontal" }, smooth: { type: "dynamic" }, arrows: { to: { enabled: false } } };
      }).filter(e => e && nodeMap[e.from] && nodeMap[e.to]);
      return { nodes: processedNodes, edges: processedEdges };
    },

    blueByWeight(v, min, max) {
      if (max <= min) return "#6ea8fe";
      const t = (v - min) / (max - min);
      return `hsl(210, 90%, ${Math.round(75 - t * 40)}%)`;
    },

    renderNetwork(nodesDS, edgesDS) {
      const container = this.$refs.graphContainer;
      const options = {
        nodes: { shape: "dot", borderWidth: 1.5, chosen: true },
        edges: { scaling: { min: 0.5, max: 5 }, smooth: { type: "dynamic" }, selectionWidth: 2 },
        physics: { enabled: true, solver: "forceAtlas2Based", forceAtlas2Based: { gravitationalConstant: -50, springLength: 120, springConstant: 0.05 }, stabilization: { iterations: 250 } },
        interaction: { hover: true, tooltipDelay: 150, zoomView: true, dragNodes: true },
      };
      if (this.network) { this.network.destroy(); this.network = null; }
      this.network = new Network(container, { nodes: nodesDS, edges: edgesDS }, options);
      this.network.on("click", params => {
        if (!this.network) return;
        clearTimeout(this.clickTimer);
        this.clickTimer = setTimeout(async () => {
          if (params.nodes.length > 0) { this.selectedNode = { ...this.nodesDS.get(params.nodes[0]) }; this.selectedEdge = null; await this.fetchNodeDetails(this.selectedNode); }
          else if (params.edges.length > 0) { this.selectedEdge = this.edgesDS.get(params.edges[0]); this.selectedNode = null; await this.fetchEdgeDetails(this.selectedEdge); }
        }, 250);
      });
      this.network.on("doubleClick", async params => {
        if (!this.network) return;
        clearTimeout(this.clickTimer);
        if (params.nodes.length === 0) return;
        await this.exploreNodeReplies(params.nodes[0]);
        if (this.network) this.network.selectNodes([params.nodes[0]], true);
      });
    },

    // ✅ METODO AGGIORNATO per gestire canali
    async searchUserReplies() {
      const q = this.query.trim();
      if (!q) return this.showToast("Inserisci un ID o username");
      
      // Reset stato
      this.channelMessage = null;
      this.chatContext = null;
      
      try {
        const res = await fetch(`http://127.0.0.1:5000/api/graph/focus?focusId=${encodeURIComponent(q)}&top=${this.depth}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        
        // ✅ Gestione messaggio per canali senza interazioni
        if (json.message) {
          this.channelMessage = json.message;
          
          // Pulisci il grafo esistente
          if (this.nodesDS) this.nodesDS.clear();
          if (this.edgesDS) this.edgesDS.clear();
          this.stats = { nodes: 0, edges: 0 };
          
          return this.showToast(json.message, 4000);
        }
        
        if (!json.nodes || json.nodes.length === 0) {
          this.chatContext = null;
          return this.showToast("Nessun risultato trovato");
        }
        
        this.exploredNodesDepth = {};
        this.initialFocusId = q;
        
        // ✅ Gestione info chat dal backend
        if (json.chat_info) {
          this.chatContext = {
            id_chat: json.chat_info.id,
            nome_chat: json.chat_info.nome,
            nome_chat_tradotto: json.chat_info.nome,
            categoria_chat: json.chat_info.categoria,
            is_channel: json.is_channel || false
          };
        } else if (!isNaN(q) || (q.startsWith("-") && !isNaN(q.substring(1)))) {
          // Fallback: prova a caricare info chat
          try {
            const cres = await fetch(`http://127.0.0.1:5000/api/chat_info/${q}`);
            if (cres.ok) {
              const chatData = await cres.json();
              if (chatData.status === "success" && chatData.data?.id_chat) {
                this.chatContext = {
                  ...chatData.data,
                  is_channel: json.is_channel || false
                };
              }
            }
          } catch {}
        }
        
        // Se non è una chat, marca il nodo focus come esplorato
        if (!this.chatContext) {
          const focusNode = json.nodes.find(n => {
            const nId = this.cleanNodeId(n.id);
            return nId === q || n.label?.toLowerCase() === q.toLowerCase();
          });
          if (focusNode) {
            this.exploredNodesDepth[this.cleanNodeId(focusNode.id)] = this.depth;
          }
        }
        
        const processed = await this.processGraphData(json.nodes || [], json.edges || [], this.chatContext ? null : q);
        this.nodesDS = new DataSet(processed.nodes);
        this.edgesDS = new DataSet(processed.edges);
        
        if (this.network) { this.network.destroy(); this.network = null; }
        this.renderNetwork(this.nodesDS, this.edgesDS);
        this.stats = { nodes: this.nodesDS.length, edges: this.edgesDS.length };
        
        const tipologia = json.is_channel ? "commentatori" : "nodi";
        this.showToast(`Caricati ${this.stats.nodes} ${tipologia} e ${this.stats.edges} collegamenti`);
        
      } catch (err) {
        console.error("Errore ricerca:", err);
        this.showToast("Errore durante la ricerca");
      }
    },

    async exploreNodeReplies(nodeId) {
      const focusClean = this.cleanNodeId(nodeId);
      const previousDepth = this.exploredNodesDepth[focusClean] || 0;
      
      if (previousDepth >= this.depth) {
        return this.showToast(`Già esplorato con profondità ${previousDepth}. Aumenta il valore per vedere più nodi.`);
      }
      
      try {
        const res = await fetch(`http://127.0.0.1:5000/api/graph/focus?focusId=${encodeURIComponent(focusClean)}&top=${this.depth}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();

        this.exploredNodesDepth[focusClean] = this.depth;
        this.updateNodeAsExplored(nodeId);

        if (!json.nodes || json.nodes.length === 0) {
          return this.showToast("Nessun altro nodo collegato trovato");
        }

        const processed = await this.processGraphData(json.nodes || [], json.edges || [], focusClean);
        
        let addedNodes = 0, addedEdges = 0;
        processed.nodes.forEach(n => { 
          if (!this.nodesDS.get(n.id)) { 
            this.nodesDS.add(n); 
            addedNodes++; 
          } 
        });
        processed.edges.forEach(e => { 
          if (!this.edgesDS.get(e.id)) { 
            this.edgesDS.add(e); 
            addedEdges++; 
          } 
        });

        if (this.network && this.nodesDS.get(nodeId)) {
          this.network.focus(nodeId, { animation: { duration: 500 }, scale: 1.3 });
        }

        this.stats = { nodes: this.nodesDS.length, edges: this.edgesDS.length };

        if (addedNodes > 0 || addedEdges > 0) {
          this.showToast(`Aggiunti ${addedNodes} nodi e ${addedEdges} collegamenti`);
        } else {
          this.showToast("Tutti i collegamenti visibili sono già nel grafo");
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
          color: this.getNodeColor(nodeId, false), 
          title: existingNode.label + ` (esplorato: ${depth})`
        });
      }
    },

    closeDetails() {
      this.selectedNode = null;
      this.selectedEdge = null;
      this.nodeDetails = null;
      this.userMessages = [];
      this.userChats = [];
      this.edgeMessages = [];
      this.nodeReplySummary = null;
      this.edgeDirectionStats = null;
      this.sentExpanded = false;
      this.receivedExpanded = false;
      this.expandedUsers = new Set();
      this.userRepliesCache = {};
      this.loadingUserReplies = null;
    },

    showToast(msg, time = 2500) { this.toast = msg; setTimeout(() => (this.toast = ""), time); },
  },

  mounted() { 
    this.fetchCategories();
    this.loadGraph(50); },
};
</script>

<style scoped>
.graph-page { padding: 1.5rem; }
.page-title { font-size: 1.8rem; font-weight: 700; margin-bottom: 0.3rem; color: #1d3b70; }
.page-description { font-size: 1rem; color: #444; margin-bottom: 1rem; }
.stats-box { display: flex; gap: 1.2rem; margin-bottom: 1rem; }
.stat-item { background: #fff; padding: 0.6rem 1rem; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); font-size: 0.95rem; }
.search-bar { display: flex; gap: 0.6rem; margin-bottom: 1rem; flex-wrap: wrap; }
.search-input { flex: 2; min-width: 200px; padding: 0.6rem 0.8rem; border: 1px solid #ccc; border-radius: 6px; font-size: 1rem; }
.depth-input { width: 80px; padding: 0.4rem; border: 1px solid #ccc; border-radius: 6px; text-align: center; font-size: 1rem; }
.search-btn { background: #3558ff; color: #fff; border: none; padding: 0.6rem 1rem; border-radius: 6px; cursor: pointer; font-weight: 600; }
.search-btn:hover { background: #2f4dd7; }
.graph-layout { display: flex; gap: 1rem; }
.graph-container { flex: 4; height: 70vh; border-radius: 8px; background: #fff; box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
.legend { flex: 1; background: #f9fbff; padding: 1rem; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); height: fit-content; min-width: 180px; }
.legend h3 { margin-bottom: 0.8rem; font-size: 1.1rem; }
.legend ul { list-style: none; padding: 0; margin: 0 0 0.8rem 0; }
.legend li { display: flex; align-items: center; margin-bottom: 0.4rem; }
.legend-color { display: inline-block; width: 16px; height: 16px; margin-right: 6px; border-radius: 4px; }
.legend-note { font-size: 0.85rem; color: #555; line-height: 1.4; }

/* ✅ Banner Chat migliorato */
.chat-banner { 
  background: #eef4ff; 
  border: 1px solid #c7ddff; 
  border-left: 6px solid #3558ff; 
  padding: 0.8rem 1.2rem; 
  margin: 1rem 0; 
  border-radius: 6px; 
  font-size: 1rem; 
  color: #1d3b70; 
  display: flex; 
  align-items: center; 
  gap: 8px; 
  flex-wrap: wrap; 
}
.chat-banner.channel-banner {
  background: #fff8e6;
  border-color: #ffd666;
  border-left-color: #faad14;
}
.chat-banner .chat-icon { font-size: 1.3rem; }
.chat-banner-content { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.chat-banner strong { color: #0d2c8d; }
.chat-banner.channel-banner strong { color: #ad6800; }
.chat-banner .chat-cat { font-style: italic; margin-left: 6px; color: #555; }

/* ✅ Avviso canale senza interazioni */
.channel-notice {
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-left: 6px solid #faad14;
  padding: 1rem 1.2rem;
  margin: 1rem 0;
  border-radius: 6px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.channel-notice .notice-icon {
  font-size: 1.5rem;
}
.channel-notice p {
  margin: 0;
  color: #614700;
  line-height: 1.5;
}

.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; z-index: 2000; }
.modal { background: #fff; padding: 1.2rem 1.5rem; border-radius: 8px; width: 520px; max-width: 95%; max-height: 85vh; overflow-y: auto; box-shadow: 0 4px 12px rgba(0,0,0,0.25); }
.modal h3 { margin-bottom: 0.8rem; display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem; }
.modal h4 { margin-top: 1rem; margin-bottom: 0.5rem; font-size: 1rem; color: #1d3b70; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
.btn-close { margin-top: 1rem; padding: 0.5rem 1rem; border: none; border-radius: 6px; background: #e63946; color: #fff; cursor: pointer; font-weight: 600; width: 100%; }
.btn-close:hover { background: #c92c3c; }
.toast { position: fixed; bottom: 1.5rem; right: 1.5rem; background: #333; color: #fff; padding: 0.7rem 1.2rem; border-radius: 6px; font-size: 0.9rem; z-index: 3000; }
.username-link { color: #3558ff; text-decoration: none; font-weight: 600; display: inline-block; margin-top: 0.8rem; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; color: #fff; font-weight: 600; }
.badge.Utente { background: #2ca02c; }
.badge.explored { background: #fab005; }
.reply-list { list-style: none; padding: 0; margin: 0.5rem 0 0 0; }
.reply-list li { padding: 0.5rem; margin-bottom: 0.5rem; border-bottom: 1px solid #eee; background: #fafafa; border-radius: 4px; }
.reply-list li:last-child { border-bottom: none; }
.reply-list p { margin: 0.2rem 0; font-size: 0.9rem; }
.reply-list em { font-size: 0.8rem; color: #555; }
.mt-8 { margin-top: 0.8rem; }
.depth-box { display: flex; flex-direction: column; align-items: center; }
.depth-label { font-size: 0.75rem; color: #555; margin-top: 2px; }

.msg-header { display: flex; align-items: flex-start; gap: 0.6rem; }
.avatar-sm { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; }
.avatar-md { width: 48px; height: 48px; border-radius: 50%; object-fit: cover; }
.avatar-placeholder { width: 48px; height: 48px; border-radius: 50%; background: #e9ecef; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; }
.msg-meta { font-size: 0.8rem; color: #666; display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.msg-text { margin: 0.4rem 0; font-size: 0.9rem; line-height: 1.4; background: #f5f5f5; padding: 0.4rem 0.6rem; border-radius: 4px; border-left: 3px solid #3558ff; }
.reply-to-name { color: #666; font-weight: normal; }

/* REPLY SUMMARY */
.reply-summary-section { margin: 1rem 0; padding: 0.8rem; background: #f8f9fa; border-radius: 8px; border: 1px solid #e9ecef; }
.reply-summary-section h4 { margin: 0 0 0.8rem 0; font-size: 1rem; color: #1d3b70; }
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
.interaction-name { color: #1d3b70; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }
.interaction-count { color: #fff; font-size: 0.75rem; background: #6c757d; padding: 0.1rem 0.5rem; border-radius: 10px; min-width: 24px; text-align: center; }
.more-items { font-style: italic; color: #888; font-size: 0.8rem; justify-content: center !important; background: transparent !important; }
.reply-balance { margin-top: 0.8rem; padding: 0.5rem; text-align: center; border-radius: 6px; font-size: 0.9rem; font-weight: 600; }
.balance-positive { background: #fff3cd; color: #856404; }
.balance-negative { background: #d4edda; color: #155724; }
.balance-neutral { background: #e2e3e5; color: #383d41; }
.loading-summary { text-align: center; padding: 1rem; color: #666; font-style: italic; }

/* EDGE VISUAL */
.edge-summary-visual { display: flex; align-items: center; justify-content: space-between; padding: 1rem; background: #f8f9fa; border-radius: 8px; margin-bottom: 1rem; gap: 0.5rem; }
.edge-user { display: flex; flex-direction: column; align-items: center; gap: 0.4rem; flex: 1; min-width: 0; }
.edge-user-name { font-size: 0.85rem; font-weight: 600; color: #1d3b70; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.edge-arrow-container { display: flex; flex-direction: column; align-items: center; gap: 0.3rem; padding: 0 0.5rem; }
.edge-total { font-size: 1.5rem; font-weight: 700; color: #3558ff; background: #eef4ff; padding: 0.3rem 0.8rem; border-radius: 20px; }
.edge-direction { font-size: 0.8rem; }
.direction-count { padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: 600; }
.direction-count.out { background: #fff5f5; color: #e63946; }
.direction-count.in { background: #f0fff4; color: #2ca02c; }

/* TELEGRAM LINK */
.tg-link { display: inline-flex; align-items: center; gap: 0.2rem; font-size: 0.75rem; font-weight: 600; color: #0088cc; background-color: #e3f2fd; padding: 0.1rem 0.4rem; border-radius: 4px; text-decoration: none; margin-left: 4px; }
.tg-link:hover { background-color: #0088cc; color: white; }
.tg-link.tg-private { color: #b45309; background-color: #fffbeb; }
.tg-link.tg-private:hover { background-color: #f59e0b; color: white; }

/* TENDINE ESPANDIBILI */
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
.mini-text { margin: 4px 0 0 0; font-size: 0.8rem; color: #444; line-height: 1.4; background: #f8f9fa; padding: 4px 8px; border-radius: 4px; border-left: 2px solid #3558ff; }
.tg-link-mini { font-size: 0.7rem; padding: 1px 4px; background: #e3f2fd; border-radius: 3px; text-decoration: none; }
.tg-link-mini:hover { background: #0088cc; color: white; }
.loading-mini { text-align: center; padding: 8px; color: #666; font-size: 0.8rem; }
.more-messages { font-style: italic; color: #888; font-size: 0.75rem; text-align: center; padding: 4px !important; }
.more-items-link { font-style: italic; color: #3558ff; font-size: 0.8rem; cursor: pointer; padding: 4px 8px; margin-top: 4px; }
.more-items-link:hover { text-decoration: underline; }
.expanded-list { margin-top: 4px; border-top: 1px dashed #ddd; padding-top: 4px; }

@media (max-width: 768px) {
  .graph-layout { flex-direction: column; }
  .legend { order: -1; }
  .graph-container { height: 50vh; }
  .edge-summary-visual { flex-direction: column; gap: 1rem; }
}
.category-select {
  padding: 0.6rem;
  border: 1px solid #ccc;
  border-radius: 6px;
  background: #fff;
  font-size: 0.95rem;
  max-width: 220px;
  cursor: pointer;
}

.category-select:focus {
  outline: none;
  border-color: #3558ff;
}
</style>