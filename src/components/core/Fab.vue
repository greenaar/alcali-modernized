<template>
  <v-speed-dial
      fixed
      bottom
      right
      direction="top"
      v-model="fab"
      transition="slide-y-reverse-transition"
  >
    <template v-slot:activator>
      <v-btn
          v-model="fab"
          color="primary"
          fab
      >
        <v-icon v-if="fab">close</v-icon>
        <v-icon v-else>menu</v-icon>
      </v-btn>
    </template>
    <template v-for="f in fabs" :key="f.tooltip">
      <v-tooltip location="left">
        <template v-slot:activator="{ props }">
          <v-btn
              fab
              dark
              small
              v-bind="props"
              :color="f.color"
              @click="emit('fab_action', f.action)"
          >
            <v-icon>{{f.icon}}</v-icon>
          </v-btn>
        </template>
        <span>{{f.tooltip}}</span>
      </v-tooltip>
    </template>
  </v-speed-dial>
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

</style>
