<template>
  <nav class="navbar">
    <!-- Logo/titolo che porta alla home (Dashboard) -->
    <router-link to="/" class="navbar-logo">Analisi Telegram</router-link>

    <!-- Link di navigazione -->
    <div class="navbar-links">
      <router-link to="/utenti" class="navbar-link">Utenti</router-link>
      <router-link to="/chat" class="navbar-link">Chat</router-link>
      <router-link to="/messaggi" class="navbar-link">Messaggi</router-link>
      <router-link to="/grafo" class="navbar-link">Grafo</router-link> 
    </div>
  </nav>
</template>

<script>
export default { name: "Navbar" };
</script>