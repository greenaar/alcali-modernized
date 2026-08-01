<template>
  <v-snackbar v-model="visible" :color="color" location="bottom center" :timeout="4000">
    {{ message }}
    <template #actions>
      <v-btn variant="text" @click="visible = false">Close</v-btn>
    </template>
  </v-snackbar>
</template>

<script>
export default {
  name: "ToastHost",
  data: () => ({ visible: false, message: "", color: "info" }),
  mounted() {
    window.addEventListener("alcali-toast", this.showToast);
  },
  beforeUnmount() {
    window.removeEventListener("alcali-toast", this.showToast);
  },
  methods: {
    showToast(event) {
      this.message = String(event.detail.message || "");
      this.color = event.detail.color || "info";
      this.visible = true;
    },
  },
};
</script>
