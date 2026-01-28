<template>
  <div id="app">
    <!-- Navbar fissa -->
    <Navbar />

    <!-- Contenitore delle pagine -->
    <div class="page-container">
      <router-view v-slot="{ Component }">
        <!-- Mantiene in cache solo le pagine più leggere -->
        <keep-alive include="Utenti,Chat,Messaggi">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </div>
  </div>
</template>

<script>
import Navbar from "./components/Navbar.vue";

export default {
  name: "App",
  components: { Navbar },
};
</script>
