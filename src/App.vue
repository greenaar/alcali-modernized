<template>
  <v-app>
    <toast-host></toast-host>
    <app-layout v-if="!layout"></app-layout>
    <simple-layout v-else></simple-layout>
  </v-app>
</template>
<script>

  import Layout from "./components/core/Layout"
  import SimpleLayout from "./components/core/SimpleLayout"
  import ToastHost from "./components/core/ToastHost"

  export default {
    computed: {
      layout() {
        return this.$route.meta.plainLayout
      },
    },
    components: {
      "app-layout": Layout,
      "simple-layout": SimpleLayout,
      "toast-host": ToastHost,
    },
  }
</script>
<style>
.legacy-list-item-content {
  flex: 1 1 auto;
  min-width: 0;
}
.legacy-list-item-action,
.legacy-list-item-avatar {
  align-items: center;
  display: inline-flex;
  flex: 0 0 auto;
  margin-inline-end: 16px;
}
  html {
    overflow-y: auto !important
  }
</style>
