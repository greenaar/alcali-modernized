<template>
  <!-- Vuetify 3 dropped the `fixed`/`bottom`/`right` props, and v-speed-dial
       renders its actions in a teleported overlay, so the wrapper is what has
       to be pinned to the corner. -->
  <div class="alcali-fab">
    <v-speed-dial
        v-model="fab"
        location="top center"
        transition="slide-y-reverse-transition"
    >
      <template v-slot:activator="{ props: activatorProps }">
        <v-btn
            v-bind="activatorProps"
            color="primary"
            icon
            size="large"
        >
          <v-icon v-if="fab">close</v-icon>
          <v-icon v-else>menu</v-icon>
        </v-btn>
      </template>
      <v-tooltip v-for="f in fabs" :key="f.tooltip" location="left">
        <template v-slot:activator="{ props: tooltipProps }">
          <v-btn
              v-bind="tooltipProps"
              icon
              size="small"
              :color="f.color"
              @click="emit('fab_action', f.action)"
          >
            <v-icon>{{f.icon}}</v-icon>
          </v-btn>
        </template>
        <span>{{f.tooltip}}</span>
      </v-tooltip>
    </v-speed-dial>
  </div>
</template>

<script>
  export default {
    name: "Fab",
    props: ['fabs'],
    methods: {
      emit(event, val) {
        this.$emit(event, val)
      }
    },
    data: () => ({
      fab: false,
    })
  }
</script>

<style scoped>
.alcali-fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 5;
}
</style>
