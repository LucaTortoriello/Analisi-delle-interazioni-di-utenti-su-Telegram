<template>
  <div class="graph-page">
    <header class="graph-header">
      <div>
        <span class="eyebrow">Network intelligence</span>
        <h1 class="page-title">Rete delle interazioni</h1>
        <p class="page-description">
          Esplora comunità, utenti ponte e intensità dei reply nell'ecosistema Telegram analizzato.
        </p>
      </div>
      <div class="graph-health" :class="{ loading: isGraphLoading }">
        <span class="health-dot"></span>
        {{ isGraphLoading ? 'Aggiornamento in corso' : 'Grafo operativo' }}
      </div>
    </header>

    <div v-if="stats" class="stats-box">
      <div class="stat-item"><span class="stat-icon nodes">●</span><div><small>Nodi visibili</small><strong>{{ stats.nodes }}</strong></div></div>
      <div class="stat-item"><span class="stat-icon edges">⌁</span><div><small>Relazioni</small><strong>{{ stats.edges }}</strong></div></div>
      <div v-if="communityAnalysis" class="stat-item"><span class="stat-icon communities">◈</span><div><small>Comunità rilevate</small><strong>{{ communityAnalysis.summary.community_count }}</strong></div></div>
      <div v-if="communityAnalysis" class="stat-item"><span class="stat-icon largest">◎</span><div><small>Comunità maggiore</small><strong>{{ communityAnalysis.summary.largest_community }}</strong></div></div>
      <div v-if="relationshipQuality" class="stat-item">
        <span class="stat-icon quality">↔</span><div><small>Relazioni reciproche</small><strong>{{ relationshipQuality.percentage }}%</strong></div>
      </div>
    </div>

    <section class="graph-toolbar">
      <div class="toolbar-search">
        <label class="field-group category-field">
          <span>Ambito</span>
          <select v-model="selectedCategory" @change="reloadGraph" class="category-select">
            <option value="">Tutte le categorie</option>
            <option v-for="cat in categories" :key="cat.categoria_chat" :value="cat.categoria_chat">
              {{ cat.categoria_chat }} ({{ cat.totale }})
            </option>
          </select>
        </label>

        <label class="field-group search-field">
          <span>Cerca nel grafo</span>
          <div class="search-input-wrap">
            <span class="search-icon">⌕</span>
            <input
              v-model="query"
              class="search-input"
              type="text"
              placeholder="ID, username oppure chat"
              @keyup.enter="searchUserReplies"
            />
          </div>
        </label>

        <label class="field-group depth-field">
          <span>Nodi</span>
          <input v-model.number="depth" class="depth-input" type="number" min="1" />
        </label>

        <button @click="searchUserReplies" class="search-btn"><span>Esplora</span><span aria-hidden="true">→</span></button>
      </div>

      <div class="view-controls">
        <span class="view-label">Vista</span>
        <button @click="toggleCommunityMode" class="view-toggle" :class="{ active: communityMode }" :disabled="!!selectedCategory" title="Colora i nodi secondo le comunità Louvain">
          <span class="toggle-indicator"></span> Comunità
        </button>
        <button @click="toggleBridgeMode" class="view-toggle bridge" :class="{ active: bridgeMode }" :disabled="!communityMode || !!selectedCategory || !communityAnalysis" title="Evidenzia gli utenti che collegano comunità differenti">
          <span class="toggle-indicator"></span> Nodi ponte
        </button>
        <button @click="toggleReciprocalOnly" class="view-toggle reciprocal" :class="{ active: reciprocalOnly }" :disabled="!lastJson?.edges?.length" title="Mostra soltanto le relazioni in entrambe le direzioni">
          <span class="toggle-indicator"></span> Solo reciproche
        </button>
      </div>
    </section>

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

    <div v-if="selectedCommunity" class="community-filter-banner">
      <div>
        <strong>Comunità isolata:</strong> {{ selectedCommunity.label }}
        <span>
          {{ stats?.nodes || 0 }} nodi visibili · {{ stats?.edges || 0 }} relazioni visibili
          <template v-if="selectedCommunity.size"> · {{ selectedCommunity.size }} membri totali</template>
        </span>
        <span v-if="selectedCommunity.internal_weight !== undefined">
          {{ selectedCommunity.internal_weight }} reply interni ·
          {{ selectedCommunity.external_weight }} reply verso altre comunità
        </span>
        <span v-if="selectedCommunity.top_chats?.length" class="community-source-chats">
          Chat principali: {{ selectedCommunity.top_chats.map(chat => chat.name).join(' · ') }}
        </span>
      </div>
      <button @click="clearCommunityFilter">Mostra tutto</button>
    </div>

    <section class="graph-stage">
      <div class="stage-header">
        <div>
          <h2>Mappa delle relazioni</h2>
          <p>Trascina per muoverti, usa la rotella per ingrandire e fai doppio clic per espandere.</p>
        </div>
        <span v-if="stats" class="visible-summary">{{ stats.nodes }} nodi · {{ stats.edges }} archi</span>
      </div>

      <div class="graph-layout">
        <div ref="graphContainer" class="graph-container"></div>
        <div v-if="isGraphLoading" class="graph-loading">
          <span class="loading-orbit"></span>
          <strong>Costruzione della rete</strong>
          <small>Calcolo comunità e relazioni…</small>
        </div>

      <aside class="legend">
        <div class="legend-header">
          <div><span class="eyebrow">Mappa colori</span><h3>Legenda</h3></div>
          <span v-if="visibleCommunities.length" class="legend-total">{{ visibleCommunities.length }}</span>
        </div>
        <ul>
          <template v-if="communityMode && visibleCommunities.length">
            <li
              v-for="community in visibleCommunities"
              :key="'community-'+community.id"
              class="community-legend-row"
              :class="{ selected: selectedCommunityId === community.id }"
            >
              <button @click="selectCommunity(community.id)" :title="`Isola ${community.label}`">
                <span class="legend-color" :style="{ background: communityColor(community.id).background }"></span>
                <span class="community-label">{{ community.label }}</span>
                <span class="community-count" title="Nodi visibili">{{ community.count }}</span>
              </button>
            </li>
          </template>
          <li v-else><span class="legend-color" style="background:#2ca02c"></span> Utente</li>
          <li v-if="bridgeMode"><span class="legend-bridge"></span> Nodo ponte principale</li>
          <li v-if="lastJson?.edges?.length"><span class="legend-edge reciprocal"></span> Reply in entrambe le direzioni</li>
          <li v-if="lastJson?.edges?.length"><span class="legend-edge one-way"></span> Reply a senso unico</li>
          <li><span class="legend-color" style="background:#ff6b6b"></span> Nodo Focus</li>
          <li><span class="legend-color" style="background:#ffd43b"></span> Già esplorato</li>
        </ul>
        <p class="legend-note">
          Lo spessore indica il numero di reply. Una linea tratteggiata rappresenta una relazione a senso unico.
        </p>
      </aside>
      </div>
    </section>

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
          <p v-if="selectedNode.community"><strong>Comunità:</strong> {{ selectedNode.community_label || 'Gruppo di utenti' }}</p>
          <p v-if="selectedNode.external_communities"><strong>Comunità collegate:</strong> {{ selectedNode.external_communities }}</p>
          <p v-if="selectedNode.bridge_score"><strong>Bridge score:</strong> {{ selectedNode.bridge_score.toFixed(2) }}</p>
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
                    <p class="mini-text">{{ truncateText(msg.testo_tradotto || msg.reply_text || msg.testo, 100) }}</p>
                    <div class="mini-translation-actions">
                      <button v-if="!msg.testo_tradotto && !msg.translating" class="btn-translate-mini" @click.stop="translateGraphMessage(msg)">Traduci</button>
                      <button v-else-if="msg.testo_tradotto" class="btn-translate-mini" @click.stop="msg.testo_tradotto = ''">Nascondi traduzione</button>
                      <span v-if="msg.translating" class="loading-mini">Traduzione...</span>
                    </div>
                    <p v-if="msg.translation_error" class="translation-error">{{ msg.translation_error }}</p>
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
                      <p class="mini-text">{{ truncateText(msg.testo_tradotto || msg.reply_text || msg.testo, 100) }}</p>
                      <div class="mini-translation-actions">
                        <button v-if="!msg.testo_tradotto && !msg.translating" class="btn-translate-mini" @click.stop="translateGraphMessage(msg)">Traduci</button>
                        <button v-else-if="msg.testo_tradotto" class="btn-translate-mini" @click.stop="msg.testo_tradotto = ''">Nascondi traduzione</button>
                        <span v-if="msg.translating" class="loading-mini">Traduzione...</span>
                      </div>
                      <p v-if="msg.translation_error" class="translation-error">{{ msg.translation_error }}</p>
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
                    <p class="mini-text">{{ truncateText(msg.testo_tradotto || msg.reply_text || msg.testo, 100) }}</p>
                    <div class="mini-translation-actions">
                      <button v-if="!msg.testo_tradotto && !msg.translating" class="btn-translate-mini" @click.stop="translateGraphMessage(msg)">Traduci</button>
                      <button v-else-if="msg.testo_tradotto" class="btn-translate-mini" @click.stop="msg.testo_tradotto = ''">Nascondi traduzione</button>
                      <span v-if="msg.translating" class="loading-mini">Traduzione...</span>
                    </div>
                    <p v-if="msg.translation_error" class="translation-error">{{ msg.translation_error }}</p>
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
                      <p class="mini-text">{{ truncateText(msg.testo_tradotto || msg.reply_text || msg.testo, 100) }}</p>
                      <div class="mini-translation-actions">
                        <button v-if="!msg.testo_tradotto && !msg.translating" class="btn-translate-mini" @click.stop="translateGraphMessage(msg)">Traduci</button>
                        <button v-else-if="msg.testo_tradotto" class="btn-translate-mini" @click.stop="msg.testo_tradotto = ''">Nascondi traduzione</button>
                        <span v-if="msg.translating" class="loading-mini">Traduzione...</span>
                      </div>
                      <p v-if="msg.translation_error" class="translation-error">{{ msg.translation_error }}</p>
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
              <div class="mini-translation-actions">
                <button v-if="!m.testo_tradotto && !m.translating" class="btn-translate-mini" @click.stop="translateGraphMessage(m)">Traduci</button>
                <button v-else-if="m.testo_tradotto" class="btn-translate-mini" @click.stop="m.testo_tradotto = ''">Nascondi traduzione</button>
                <span v-if="m.translating" class="loading-mini">Traduzione...</span>
              </div>
              <p v-if="m.translation_error" class="translation-error">{{ m.translation_error }}</p>
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

        <div v-if="edgeDirectionStats" class="edge-quality-card">
          <div class="edge-quality-heading">
            <span class="quality-badge" :class="edgeDirectionStats.reciprocal ? 'reciprocal' : 'one-way'">
              {{ edgeDirectionStats.reciprocal ? '↔ Relazione reciproca' : '→ Relazione a senso unico' }}
            </span>
            <strong>{{ Math.round(edgeDirectionStats.reciprocity * 100) }}% equilibrio</strong>
          </div>
          <div class="quality-track">
            <span :style="{ width: `${Math.round(edgeDirectionStats.reciprocity * 100)}%` }"></span>
          </div>
          <small>
            Verificata su {{ edgeDirectionStats.total }} reply con corrispondenza del messaggio originale nella stessa chat.
          </small>
        </div>

        <div v-if="edgeMessagesLoading" class="loading-summary">Caricamento delle evidenze…</div>

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
              <div class="mini-translation-actions">
                <button v-if="!m.testo_tradotto && !m.translating" class="btn-translate-mini" @click.stop="translateGraphMessage(m)">Traduci</button>
                <button v-else-if="m.testo_tradotto" class="btn-translate-mini" @click.stop="m.testo_tradotto = ''">Nascondi traduzione</button>
                <span v-if="m.translating" class="loading-mini">Traduzione...</span>
              </div>
              <p v-if="m.translation_error" class="translation-error">{{ m.translation_error }}</p>
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
import { franc } from "franc-min";

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
      communityMode: true,
      communityAnalysis: null,
      selectedCommunityId: null,
      bridgeMode: false,
      reciprocalOnly: false,
      isGraphLoading: false,
    };
  },

  computed: {
    visibleCommunities() {
      if (!this.communityMode || !this.lastJson?.nodes) return [];
      const communities = new Map();
      for (const node of this.lastJson.nodes) {
        if (!node.community) continue;
        const existing = communities.get(node.community);
        if (existing) {
          existing.count += 1;
        } else {
          communities.set(node.community, {
            id: node.community,
            label: node.community_label || 'Gruppo di utenti',
            count: 1,
          });
        }
      }
      return [...communities.values()].sort((a, b) => b.count - a.count).slice(0, 10);
    },
    selectedCommunity() {
      const visible = this.visibleCommunities.find(community => community.id === this.selectedCommunityId);
      if (!visible) return null;
      const details = this.communityAnalysis?.communities?.find(
        community => community.id === this.selectedCommunityId
      );
      return { ...(details || {}), ...visible };
    },
    relationshipQuality() {
      const edges = this.lastJson?.edges || [];
      if (!edges.length) return null;
      const reciprocal = edges.filter(edge => edge.reciprocal).length;
      return {
        reciprocal,
        total: edges.length,
        percentage: Math.round((reciprocal / edges.length) * 100),
      };
    },
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

    focusGraphUrl(focusId) {
      const params = new URLSearchParams({
        focusId: String(focusId),
        top: String(this.depth),
      });
      if (this.selectedCategory) params.set('category', this.selectedCategory);
      return `http://127.0.0.1:5000/api/graph/focus?${params.toString()}`;
    },

    communityColor(communityId) {
      const hue = (Number(communityId) * 137.508) % 360;
      return {
        background: `hsl(${hue}, 68%, 58%)`,
        border: `hsl(${hue}, 72%, 35%)`,
        highlight: { background: `hsl(${hue}, 75%, 68%)`, border: `hsl(${hue}, 72%, 30%)` },
        hover: { background: `hsl(${hue}, 75%, 64%)`, border: `hsl(${hue}, 72%, 32%)` },
      };
    },

    toggleCommunityMode() {
      this.communityMode = !this.communityMode;
      this.selectedCommunityId = null;
      if (!this.communityMode) this.bridgeMode = false;
      this.loadGraph(50);
    },

    async toggleBridgeMode() {
      this.bridgeMode = !this.bridgeMode;
      await this.renderCurrentGraph();
    },

    async toggleReciprocalOnly() {
      this.reciprocalOnly = !this.reciprocalOnly;
      await this.renderCurrentGraph();
    },

    async selectCommunity(communityId) {
      this.selectedCommunityId = this.selectedCommunityId === communityId ? null : communityId;
      await this.renderCurrentGraph();
    },

    async clearCommunityFilter() {
      this.selectedCommunityId = null;
      await this.renderCurrentGraph();
    },

    async renderCurrentGraph() {
      if (!this.lastJson) return;
      let nodes = this.lastJson.nodes || [];
      let edges = this.lastJson.edges || [];

      if (this.selectedCommunityId) {
        nodes = nodes.filter(node => node.community === this.selectedCommunityId);
        const visibleNodeIds = new Set(nodes.map(node => node.id));
        edges = edges.filter(edge => visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to));
      }

      if (this.reciprocalOnly) {
        edges = edges.filter(edge => edge.reciprocal);
        const connectedNodeIds = new Set(edges.flatMap(edge => [edge.from, edge.to]));
        nodes = nodes.filter(node => connectedNodeIds.has(node.id));
      }

      const processed = await this.processGraphData(nodes, edges);
      this.nodesDS = new DataSet(processed.nodes);
      this.edgesDS = new DataSet(processed.edges);
      this.stats = { nodes: processed.nodes.length, edges: processed.edges.length };
      this.renderNetwork(this.nodesDS, this.edgesDS);
    },
    
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

    async translateGraphMessage(message) {
      const text = message?.reply_text || message?.testo || "";
      if (!text) return;
      message.translating = true;
      message.translation_error = "";
      try {
        const res = await fetch("http://127.0.0.1:5000/api/traduci", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ q: text, source: franc(text) }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        message.testo_tradotto = data.translatedText;
      } catch (error) {
        message.translation_error = error.message || "Traduzione non disponibile";
      } finally {
        message.translating = false;
      }
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
          const [res, mres, summaryRes] = await Promise.all([
            fetch(`http://127.0.0.1:5000/api/utente/${id}`),
            fetch(`http://127.0.0.1:5000/api/messaggi_utente/${id}?limit=3&offset=0`),
            fetch(`http://127.0.0.1:5000/api/reply_summary/${id}`),
          ]);
          if (res.ok) { const data = await res.json(); this.nodeDetails = data.user || null; this.userChats = data.chats || []; }
          if (mres.ok) {
            const data = await mres.json();
            this.userMessages = (data.data || []).slice(0, 3);
          }
          if (summaryRes.ok) {
            this.nodeReplySummary = await summaryRes.json();
          }
        }
      } catch (err) { console.error("Errore fetch dettagli nodo:", err); this.nodeDetails = { errore: "Impossibile caricare" }; }
      finally { this.nodeReplySummaryLoading = false; }
    },

    async fetchNodeReplySummary(userId) {
      try {
        const res = await fetch(`http://127.0.0.1:5000/api/reply_summary/${userId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        this.nodeReplySummary = await res.json();
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
      this.edgeDirectionStats = edge?.forward !== undefined
        ? {
            aToB: Number(edge.forward || 0),
            bToA: Number(edge.reverse || 0),
            total: Number(edge.value || 0),
            reciprocal: Boolean(edge.reciprocal),
            reciprocity: Number(edge.reciprocity || 0),
          }
        : null;
      this.edgeMessagesLoading = true;
      try {
        if (!edge?.from || !edge?.to) return;
        const fromId = this.cleanNodeId(edge.from);
        const toId = this.cleanNodeId(edge.to);
        const res = await fetch(`http://127.0.0.1:5000/api/graph/edge/${fromId}/${toId}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);

        this.edgeDirectionStats = {
          aToB: Number(data.stats?.forward || 0),
          bToA: Number(data.stats?.reverse || 0),
          total: Number(data.stats?.total || 0),
          reciprocal: Boolean(data.stats?.reciprocal),
          reciprocity: Number(data.stats?.reciprocity || 0),
        };
        this.edgeMessages = data.messages || [];
        this.selectedEdge = {
          ...edge,
          value: this.edgeDirectionStats.total,
          fromNome: data.from_user?.nome,
          fromUser: data.from_user?.username,
          avatar_from: data.from_user?.avatar_url,
          toNome: data.to_user?.nome,
          toUser: data.to_user?.username,
          avatar_to: data.to_user?.avatar_url,
        };
      } catch (err) { console.error("Errore fetch arco:", err); }
      finally { this.edgeMessagesLoading = false; }
    },

    async loadGraph(limit = 300) {
  this.isGraphLoading = true;
  try {
    // 1. Costruisci l'URL base con il limite
    let url = `http://127.0.0.1:5000/api/graph?limit=${limit}`;

    if (this.communityMode && !this.selectedCategory) {
      url += "&communities=1";
    }

    // 2. Aggiungi il parametro category se selezionato
    if (this.selectedCategory) {
      url += `&category=${encodeURIComponent(this.selectedCategory)}`;
    }

    // 3. Esegui la chiamata fetch all'URL aggiornato
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    const json = await res.json();
    this.lastJson = json;
    this.selectedCommunityId = null;
    this.exploredNodesDepth = {};
    this.initialFocusId = null;
    this.chatContext = null;
    this.channelMessage = null;
    this.communityAnalysis = json.community_analysis || null;
    if (!this.communityAnalysis) this.bridgeMode = false;
    await this.renderCurrentGraph();
  } catch (err) { 
    console.error("Errore caricamento grafo:", err); 
    this.showToast("Errore nel caricamento del grafo"); 
  } finally {
    this.isGraphLoading = false;
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
      const bridgeNodeIds = new Set(
        this.bridgeMode
          ? [...nodes]
              .filter(node => Number(node.bridge_score) > 0)
              .sort((a, b) => Number(b.bridge_score) - Number(a.bridge_score))
              .slice(0, 12)
              .map(node => node.id)
          : []
      );
      const seen = new Set();
      const processedNodes = (nodes || []).map(n => {
        if (seen.has(n.id)) return null;
        seen.add(n.id);
        const cleanId = this.cleanNodeId(n.id);
        const safeLabel = n.label && n.label.trim() !== "" ? n.label : String(n.id);
        const displayLabel = /^\d{9,}$/.test(safeLabel) ? `…${safeLabel.slice(-6)}` : safeLabel;
        const exploredDepth = this.exploredNodesDepth[cleanId] || 0;
        const isFocus = focusId && cleanId === String(focusId);
        const isBridge = bridgeNodeIds.has(n.id);
        let nodeColor = n.color || (
          this.communityMode && n.community
            ? this.communityColor(n.community)
            : this.getNodeColor(n.id, isFocus)
        );
        if (isFocus) nodeColor = this.getNodeColor(n.id, true);
        if (exploredDepth > 0 && !isFocus) nodeColor = this.getNodeColor(n.id, false);
        if (isBridge && !isFocus && exploredDepth === 0) {
          nodeColor = {
            ...nodeColor,
            border: '#f08c00',
            highlight: { ...(nodeColor.highlight || {}), border: '#e67700' },
            hover: { ...(nodeColor.hover || {}), border: '#e67700' },
          };
        }
        
        let title = safeLabel;
        if (isFocus) title += " (focus)";
        else if (exploredDepth > 0) title += ` (esplorato: ${exploredDepth})`;
        if (n.community) title += `\n${n.community_label || 'Gruppo di utenti'}`;
        if (n.external_communities) title += `\nCollega ${n.external_communities} comunità`;
        if (isBridge) title += `\nNodo ponte principale · score ${Number(n.bridge_score).toFixed(2)}`;
        
        return {
          ...n,
          label: displayLabel,
          font: { color: "#000" },
          shape: isBridge ? "diamond" : "dot",
          borderWidth: isBridge ? 4 : 1.5,
          shadow: isBridge ? { enabled: true, color: 'rgba(240, 140, 0, 0.35)', size: 12 } : false,
          is_bridge: isBridge,
          value: n.weighted_degree ? Math.log1p(n.weighted_degree) : n.value,
          scaling: { min: 10, max: 45 },
          title,
          color: nodeColor,
        };
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
        const reciprocal = Boolean(e.reciprocal);
        const forward = Number(e.forward || 0);
        const reverse = Number(e.reverse || 0);
        return {
          ...e,
          id: normalizedId,
          value,
          reciprocal,
          width: Math.max(1, Math.log2(value + 1)),
          color: { color, highlight: '#1d4ed8', hover: '#2563eb', opacity: reciprocal ? 0.82 : 0.58 },
          label: value ? `${reciprocal ? '↔ ' : ''}${value}` : "",
          title: reciprocal
            ? `${forward} reply →\n${reverse} reply ←\nReciprocità ${Math.round(Number(e.reciprocity || 0) * 100)}%`
            : `${value} reply in una sola direzione`,
          dashes: reciprocal ? false : [8, 7],
          font: { size: 10, color: '#475569', strokeWidth: 4, strokeColor: '#ffffff', align: "horizontal" },
          smooth: { type: "dynamic" },
          arrows: {
            to: { enabled: !reciprocal && forward > 0, scaleFactor: 0.55 },
            from: { enabled: !reciprocal && reverse > 0, scaleFactor: 0.55 },
          },
        };
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
      this.lastJson = null;
      this.communityAnalysis = null;
      this.selectedCommunityId = null;
      this.bridgeMode = false;
      this.reciprocalOnly = false;
      
      try {
        const res = await fetch(this.focusGraphUrl(q));
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
        const res = await fetch(this.focusGraphUrl(focusClean));
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
.graph-page { max-width: 1800px; margin: 0 auto; padding: 2rem clamp(1rem, 2.4vw, 2.5rem) 3rem; }
.graph-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 2rem; margin-bottom: 1.4rem; }
.eyebrow { display: block; margin-bottom: 0.35rem; color: #4f46e5; font-size: 0.68rem; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; }
.page-title { margin: 0 0 0.35rem; color: #0f172a; font-size: clamp(2rem, 3vw, 2.65rem); line-height: 1.08; letter-spacing: -0.04em; }
.page-description { max-width: 760px; margin: 0; color: #64748b; font-size: 0.98rem; }
.graph-health { display: inline-flex; align-items: center; gap: 0.55rem; flex: 0 0 auto; margin-top: 0.35rem; padding: 0.48rem 0.75rem; border: 1px solid #d1fae5; border-radius: 999px; background: #ecfdf5; color: #047857; font-size: 0.76rem; font-weight: 700; }
.graph-health.loading { border-color: #dbeafe; background: #eff6ff; color: #1d4ed8; }
.health-dot { width: 7px; height: 7px; border-radius: 50%; background: #10b981; box-shadow: 0 0 0 4px rgba(16,185,129,0.12); }
.graph-health.loading .health-dot { background: #3b82f6; box-shadow: 0 0 0 4px rgba(59,130,246,0.12); animation: pulse 1.1s ease-in-out infinite; }

.stats-box { display: grid; grid-template-columns: repeat(5, minmax(145px, 1fr)); gap: 0.75rem; margin-bottom: 1rem; }
.stat-item { display: flex; align-items: center; gap: 0.75rem; min-height: 72px; padding: 0.8rem 0.95rem; border: 1px solid #e2e8f0; border-radius: 13px; background: #fff; box-shadow: 0 1px 2px rgba(15,23,42,0.03); }
.stat-item > div { display: flex; flex-direction: column; min-width: 0; }
.stat-item small { color: #64748b; font-size: 0.7rem; font-weight: 650; letter-spacing: 0.02em; white-space: nowrap; }
.stat-item strong { color: #0f172a; font-size: 1.3rem; line-height: 1.2; letter-spacing: -0.03em; }
.stat-icon { display: grid; place-items: center; flex: 0 0 34px; width: 34px; height: 34px; border-radius: 10px; font-size: 1rem; font-weight: 800; }
.stat-icon.nodes { background: #eef2ff; color: #4f46e5; }
.stat-icon.edges { background: #eff6ff; color: #2563eb; }
.stat-icon.communities { background: #f5f3ff; color: #7c3aed; }
.stat-icon.largest { background: #fff7ed; color: #ea580c; }
.stat-icon.quality { background: #ecfdf5; color: #059669; }

.graph-toolbar { margin-bottom: 1rem; overflow: hidden; border: 1px solid #dfe6ef; border-radius: 15px; background: rgba(255,255,255,0.96); box-shadow: 0 4px 18px rgba(15,23,42,0.045); }
.toolbar-search { display: grid; grid-template-columns: minmax(170px, 0.72fr) minmax(300px, 2fr) 82px auto; align-items: end; gap: 0.75rem; padding: 0.9rem; }
.field-group { display: flex; flex-direction: column; gap: 0.35rem; min-width: 0; }
.field-group > span { color: #64748b; font-size: 0.68rem; font-weight: 750; letter-spacing: 0.045em; text-transform: uppercase; }
.category-select, .search-input, .depth-input { width: 100%; height: 42px; border: 1px solid #dbe3ed; border-radius: 9px; outline: 0; background: #f8fafc; color: #1e293b; font: inherit; font-size: 0.88rem; transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease; }
.category-select { max-width: none; padding: 0 0.75rem; cursor: pointer; }
.search-input { min-width: 0; padding: 0 0.8rem 0 2.45rem; }
.depth-input { padding: 0 0.5rem; text-align: center; }
.category-select:focus, .search-input:focus, .depth-input:focus { border-color: #818cf8; background: #fff; box-shadow: 0 0 0 3px rgba(99,102,241,0.12); }
.search-input-wrap { position: relative; }
.search-icon { position: absolute; top: 50%; left: 0.85rem; z-index: 1; transform: translateY(-50%); color: #94a3b8; font-size: 1.15rem; pointer-events: none; }
.search-btn { display: inline-flex; align-items: center; justify-content: center; gap: 0.7rem; height: 42px; padding: 0 1.1rem; border: 0; border-radius: 9px; background: linear-gradient(135deg, #4f46e5, #2563eb); color: #fff; cursor: pointer; font-weight: 750; box-shadow: 0 5px 12px rgba(79,70,229,0.2); transition: transform 0.18s ease, box-shadow 0.18s ease; }
.search-btn:hover { transform: translateY(-1px); box-shadow: 0 8px 16px rgba(79,70,229,0.25); }
.view-controls { display: flex; align-items: center; gap: 0.45rem; min-height: 52px; padding: 0.6rem 0.9rem; border-top: 1px solid #edf1f6; background: #fbfcfe; }
.view-label { margin-right: 0.3rem; color: #94a3b8; font-size: 0.68rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; }
.view-toggle { display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.42rem 0.7rem; border: 1px solid transparent; border-radius: 999px; background: transparent; color: #64748b; cursor: pointer; font-size: 0.78rem; font-weight: 700; transition: all 0.18s ease; }
.view-toggle:hover:not(:disabled) { border-color: #dbe3ed; background: #fff; color: #334155; }
.view-toggle.active { border-color: #c7d2fe; background: #eef2ff; color: #4338ca; }
.view-toggle.bridge.active { border-color: #fed7aa; background: #fff7ed; color: #c2410c; }
.view-toggle.reciprocal.active { border-color: #a7f3d0; background: #ecfdf5; color: #047857; }
.view-toggle:disabled { opacity: 0.42; cursor: not-allowed; }
.toggle-indicator { width: 7px; height: 7px; border-radius: 50%; background: #cbd5e1; }
.view-toggle.active .toggle-indicator { background: currentColor; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }

.community-filter-banner { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin: 0 0 1rem; padding: 0.85rem 1rem; border: 1px solid #ddd6fe; border-radius: 12px; background: linear-gradient(135deg, #faf5ff, #eef2ff); color: #3730a3; }
.community-filter-banner span { display: block; margin-top: 0.16rem; color: #6d5f91; font-size: 0.8rem; }
.community-filter-banner .community-source-chats { max-width: 900px; color: #514373; font-style: italic; }
.community-filter-banner button { flex: 0 0 auto; border: 1px solid #c4b5fd; border-radius: 8px; background: rgba(255,255,255,0.8); color: #5b21b6; padding: 0.48rem 0.75rem; cursor: pointer; font-weight: 750; }

.graph-stage { overflow: hidden; border: 1px solid #dfe6ef; border-radius: 16px; background: #fff; box-shadow: 0 12px 35px rgba(15,23,42,0.07); }
.stage-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; min-height: 68px; padding: 0.8rem 1.1rem; border-bottom: 1px solid #edf1f6; }
.stage-header h2 { margin: 0 0 0.15rem; color: #172033; font-size: 1rem; letter-spacing: -0.01em; }
.stage-header p { margin: 0; color: #8491a3; font-size: 0.75rem; }
.visible-summary { flex: 0 0 auto; padding: 0.35rem 0.62rem; border-radius: 999px; background: #f1f5f9; color: #64748b; font-size: 0.72rem; font-weight: 750; }
.graph-layout { position: relative; min-height: 610px; }
.graph-container { width: 100%; height: 70vh; min-height: 610px; background-color: #fbfdff; background-image: radial-gradient(circle at 15% 20%, rgba(99,102,241,0.055), transparent 28%), radial-gradient(circle at 82% 72%, rgba(14,165,233,0.045), transparent 30%), linear-gradient(rgba(226,232,240,0.38) 1px, transparent 1px), linear-gradient(90deg, rgba(226,232,240,0.38) 1px, transparent 1px); background-size: auto, auto, 28px 28px, 28px 28px; }
.graph-loading { position: absolute; inset: 0; z-index: 5; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.35rem; background: rgba(248,250,252,0.88); backdrop-filter: blur(3px); color: #334155; }
.graph-loading small { color: #94a3b8; }
.loading-orbit { width: 32px; height: 32px; margin-bottom: 0.4rem; border: 3px solid #dbeafe; border-top-color: #4f46e5; border-radius: 50%; animation: spin 0.8s linear infinite; }
.legend { position: absolute; top: 1rem; right: 1rem; z-index: 4; width: min(300px, calc(100% - 2rem)); max-height: calc(70vh - 2rem); overflow-y: auto; padding: 0.9rem; border: 1px solid rgba(203,213,225,0.85); border-radius: 13px; background: rgba(255,255,255,0.91); box-shadow: 0 10px 30px rgba(15,23,42,0.1); backdrop-filter: blur(12px); }
.legend-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 0.55rem; }
.legend-header .eyebrow { margin-bottom: 0.05rem; font-size: 0.58rem; }
.legend h3 { margin: 0; color: #1e293b; font-size: 0.98rem; }
.legend-total { display: grid; place-items: center; min-width: 25px; height: 25px; padding: 0 0.35rem; border-radius: 8px; background: #eef2ff; color: #4f46e5; font-size: 0.72rem; font-weight: 800; }
.legend ul { list-style: none; padding: 0; margin: 0 0 0.65rem; }
.legend li { display: flex; align-items: flex-start; margin-bottom: 0.28rem; color: #475569; font-size: 0.78rem; line-height: 1.3; }
.legend-color { display: inline-block; flex: 0 0 12px; width: 12px; height: 12px; margin: 2px 7px 0 0; border-radius: 4px; box-shadow: inset 0 0 0 1px rgba(15,23,42,0.08); }
.community-label { display: -webkit-box; overflow: hidden; overflow-wrap: anywhere; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.community-legend-row { border-radius: 7px; transition: background 0.15s ease; }
.community-legend-row:hover, .community-legend-row.selected { background: #eef2ff; }
.community-legend-row button { display: flex; align-items: flex-start; width: 100%; border: 0; padding: 0.38rem 0.4rem; background: transparent; color: inherit; text-align: left; cursor: pointer; font: inherit; }
.community-count { flex: 0 0 auto; min-width: 23px; margin-left: auto; padding: 0.08rem 0.33rem; border-radius: 999px; background: #f1f5f9; color: #64748b; font-size: 0.65rem; font-weight: 800; text-align: center; }
.legend-bridge { display: inline-block; flex: 0 0 11px; width: 11px; height: 11px; margin: 2px 8px 0 2px; border: 2px solid #f08c00; background: #fff4e6; transform: rotate(45deg); }
.legend-edge { display: inline-block; flex: 0 0 18px; width: 18px; height: 0; margin: 7px 7px 0 0; border-top: 2px solid #3b82f6; }
.legend-edge.one-way { border-top-style: dashed; opacity: 0.65; }
.legend-note { margin: 0; padding-top: 0.65rem; border-top: 1px solid #edf1f6; color: #7b8798; font-size: 0.7rem; line-height: 1.45; }

@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 50% { opacity: 0.45; } }
@keyframes drawer-in { from { opacity: 0; transform: translateX(28px); } to { opacity: 1; transform: translateX(0); } }

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

.modal-overlay { position: fixed; inset: 0; z-index: 2000; display: flex; align-items: stretch; justify-content: flex-end; background: rgba(15,23,42,0.32); backdrop-filter: blur(3px); }
.modal { width: min(620px, 96vw); max-width: none; max-height: 100vh; overflow-y: auto; padding: 1.6rem 1.75rem 2rem; border-left: 1px solid #e2e8f0; border-radius: 18px 0 0 18px; background: #fff; box-shadow: -18px 0 50px rgba(15,23,42,0.16); animation: drawer-in 0.22s ease-out; }
.modal h3 { margin-bottom: 1rem; padding-bottom: 0.85rem; border-bottom: 1px solid #edf1f6; display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem; color: #172033; }
.modal h4 { margin-top: 1rem; margin-bottom: 0.5rem; font-size: 1rem; color: #1d3b70; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
.btn-close { margin-top: 1rem; padding: 0.65rem 1rem; border: 1px solid #dbe3ed; border-radius: 9px; background: #f8fafc; color: #334155; cursor: pointer; font-weight: 700; width: 100%; }
.btn-close:hover { border-color: #cbd5e1; background: #f1f5f9; }
.toast { position: fixed; bottom: 1.5rem; right: 1.5rem; background: #172033; color: #fff; padding: 0.72rem 1rem; border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; box-shadow: 0 12px 30px rgba(15,23,42,0.25); font-size: 0.85rem; z-index: 3000; }
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
.edge-quality-card { margin-bottom: 1rem; padding: 0.85rem; border: 1px solid #e2e8f0; border-radius: 11px; background: #f8fafc; }
.edge-quality-heading { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.6rem; }
.edge-quality-heading strong { color: #334155; font-size: 0.78rem; }
.quality-badge { display: inline-flex; align-items: center; padding: 0.25rem 0.55rem; border-radius: 999px; font-size: 0.7rem; font-weight: 800; }
.quality-badge.reciprocal { border: 1px solid #a7f3d0; background: #ecfdf5; color: #047857; }
.quality-badge.one-way { border: 1px solid #fed7aa; background: #fff7ed; color: #c2410c; }
.quality-track { height: 6px; margin-bottom: 0.5rem; overflow: hidden; border-radius: 999px; background: #e2e8f0; }
.quality-track span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #60a5fa, #10b981); transition: width 0.25s ease; }
.edge-quality-card small { display: block; color: #64748b; font-size: 0.7rem; line-height: 1.4; }

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
.mini-translation-actions { display: flex; align-items: center; gap: 0.5rem; margin-top: 0.35rem; }
.btn-translate-mini { border: 1px solid #9bb7ff; background: #eef4ff; color: #244ea2; border-radius: 5px; padding: 0.25rem 0.55rem; font-size: 0.75rem; cursor: pointer; }
.btn-translate-mini:hover { background: #dce8ff; }
.translation-error { margin: 0.3rem 0 0; color: #b42318; font-size: 0.75rem; }
.tg-link-mini { font-size: 0.7rem; padding: 1px 4px; background: #e3f2fd; border-radius: 3px; text-decoration: none; }
.tg-link-mini:hover { background: #0088cc; color: white; }
.loading-mini { text-align: center; padding: 8px; color: #666; font-size: 0.8rem; }
.more-messages { font-style: italic; color: #888; font-size: 0.75rem; text-align: center; padding: 4px !important; }
.more-items-link { font-style: italic; color: #3558ff; font-size: 0.8rem; cursor: pointer; padding: 4px 8px; margin-top: 4px; }
.more-items-link:hover { text-decoration: underline; }
.expanded-list { margin-top: 4px; border-top: 1px dashed #ddd; padding-top: 4px; }

@media (max-width: 1100px) {
  .stats-box { grid-template-columns: repeat(3, minmax(145px, 1fr)); }
  .toolbar-search { grid-template-columns: minmax(170px, 0.8fr) minmax(260px, 1.7fr) 78px auto; }
}

@media (max-width: 768px) {
  .graph-page { padding: 1rem 0.5rem 2rem; }
  .graph-header { flex-direction: column; gap: 0.7rem; }
  .page-title { font-size: 2rem; }
  .graph-health { margin-top: 0; }
  .stats-box { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stat-item { min-height: 65px; padding: 0.65rem; }
  .stat-item small { white-space: normal; }
  .toolbar-search { grid-template-columns: 1fr 72px; }
  .category-field, .search-field { grid-column: 1 / -1; }
  .search-btn { width: 100%; }
  .view-controls { flex-wrap: wrap; }
  .view-label { width: 100%; }
  .stage-header { align-items: flex-start; }
  .stage-header p { display: none; }
  .graph-layout { display: flex; flex-direction: column; min-height: 0; }
  .graph-container { height: 56vh; min-height: 440px; }
  .legend { position: relative; top: auto; right: auto; width: auto; max-height: none; margin: 0.75rem; order: 2; }
  .graph-loading { bottom: auto; height: 56vh; min-height: 440px; }
  .community-filter-banner { align-items: flex-start; flex-direction: column; }
  .modal { width: 100%; border-radius: 0; padding: 1.2rem 1rem 1.5rem; }
  .edge-summary-visual { flex-direction: column; gap: 1rem; }
}
</style>
