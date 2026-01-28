import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import './assets/global.css'; 


// Creazione app Vue
const app = createApp(App);

// Usa il router per la navigazione
app.use(router);

// Monta l'app
app.mount('#app');
