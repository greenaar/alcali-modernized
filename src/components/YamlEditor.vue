<template>
  <pre v-if="readOnly" class="yaml-editor" :class="{ collapsed }">{{ content }}</pre>
  <textarea
    v-else
    class="yaml-editor yaml-editor-input"
    :value="content"
    spellcheck="false"
    @input="updateValue"
  ></textarea>
</template>

<script>
export default {
  name: "YamlEditor",
  props: {
    modelValue: { type: String, default: "" },
    readOnly: { type: Boolean, default: false },
    collapsed: { type: Boolean, default: false },
  },
  computed: {
    content() {
      return this.modelValue || "";
    },
  },
  methods: {
    updateValue(event) {
      this.$emit("update:modelValue", event.target.value);
    },
  },
};
</script>

<style scoped>
.yaml-editor {
  box-sizing: border-box;
  width: 100%;
  min-height: 12rem;
  margin: 0;
  padding: 1rem;
  overflow: auto;
  border: 1px solid rgba(127, 127, 127, 0.35);
  border-radius: 4px;
  background: #111827;
  color: #e5e7eb;
  font: 0.875rem/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
  white-space: pre;
}
.yaml-editor-input { resize: vertical; }
.collapsed { max-height: 3.5rem; min-height: 3.5rem; }
</style>
