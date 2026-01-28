import { createRouter, createWebHistory } from 'vue-router';

import Dashboard from '../components/Dashboard.vue';
import Utenti from '../components/Utenti.vue';
import Chat from '../components/Chat.vue';
import Messaggi from '../components/Messaggi.vue';

import Grafo from '../components/Grafo.vue';           // 🔵 grafo generale
import GrafoFiltrato from '../components/GrafoFiltrato.vue'; // 🔵 grafo filtrato

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: Dashboard,
    meta: { title: 'Dashboard - Analisi Telegram' }
  },

  {
    path: '/utenti',
    name: 'Utenti',
    component: Utenti,
    meta: { title: 'Utenti - Analisi Telegram' }
  },
  {
    path: '/utenti/:userId',
    name: 'UtenteDettaglio',
    component: Utenti,
    meta: { title: 'Utente - Analisi Telegram' }
  },

  {
    path: '/chat',
    name: 'Chat',
    component: Chat,
    meta: { title: 'Chat - Analisi Telegram' }
  },

  {
    path: '/messaggi/:chatId?',
    name: 'Messaggi',
    component: Messaggi,
    meta: { title: 'Messaggi - Analisi Telegram' }
  },

  {
    path: '/messaggi_utente/:userId',
    name: 'MessaggiUtente',
    component: Messaggi,
    meta: { title: 'Messaggi Utente - Analisi Telegram' }
  },

  // 🔵 GRAFO GENERALE
  {
    path: '/grafo',
    name: 'Grafo',
    component: Grafo,
    meta: { title: 'Grafo - Analisi Telegram' }
  },

  // 🔵 GRAFO FILTRATO (keyword/chat/data)
  {
    path: '/grafo-filtrato',
    name: 'GrafoFiltrato',
    component: GrafoFiltrato,
    meta: { title: 'Grafo filtrato - Analisi Telegram' }
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

router.beforeEach((to, _, next) => {
  document.title = to.meta.title || 'Analisi Telegram';
  next();
});

export default router;
