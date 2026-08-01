<template>
  <v-data-table
    v-bind="$attrs"
    :headers="modernHeaders"
    :sort-by="modernSortBy"
    @update:sort-by="updateSort"
  >
    <template v-for="(_, slotName) in $slots" #[slotName]="slotProps">
      <slot :name="slotName" v-bind="normalizeSlotProps(slotProps)" />
    </template>
  </v-data-table>
</template>

<script>
export default {
  name: "LegacyDataTable",
  inheritAttrs: false,
  props: {
    headers: { type: Array, default: () => [] },
    sortBy: { type: [String, Array], default: () => [] },
    sortDesc: { type: [Boolean, Array], default: false },
  },
  emits: ["update:sortBy", "update:sortDesc"],
  computed: {
    modernHeaders() {
      return this.headers.map(header => ({
        ...header,
        title: header.title || header.text,
        key: header.key || header.value,
      }))
    },
    modernSortBy() {
      if (Array.isArray(this.sortBy)) return this.sortBy
      if (!this.sortBy) return []
      const descending = Array.isArray(this.sortDesc) ? this.sortDesc[0] : this.sortDesc
      return [{ key: this.sortBy, order: descending ? "desc" : "asc" }]
    },
  },
  methods: {
    normalizeSlotProps(slotProps) {
      if (!slotProps || !slotProps.item) return slotProps || {}
      return { ...slotProps, item: slotProps.item.raw || slotProps.item }
    },
    updateSort(sortBy) {
      const first = sortBy && sortBy[0]
      this.$emit("update:sortBy", first ? first.key : null)
      this.$emit("update:sortDesc", first ? first.order === "desc" : false)
    },
  },
}
</script>
