<template>
  <v-data-table
    v-bind="$attrs"
    :headers="modernHeaders"
    :sort-by="effectiveSortBy"
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
  data() {
    return {
      // Where the sort goes when the caller passes a plain `sort-by` rather
      // than binding it. Without this the column headers emitted an update
      // nobody listened to, the prop never moved, and the table re-rendered
      // in its original order - so sorting looked broken.
      internalSortBy: null,
    }
  },
  computed: {
    modernHeaders() {
      return this.headers.map(header => ({
        ...header,
        title: header.title || header.text,
        key: header.key || header.value,
      }))
    },
    propSortBy() {
      if (Array.isArray(this.sortBy)) return this.sortBy
      if (!this.sortBy) return []
      const descending = Array.isArray(this.sortDesc) ? this.sortDesc[0] : this.sortDesc
      return [{ key: this.sortBy, order: descending ? "desc" : "asc" }]
    },
    effectiveSortBy() {
      return this.internalSortBy === null ? this.propSortBy : this.internalSortBy
    },
  },
  watch: {
    // A caller that does bind the prop stays in charge: when it sends a new
    // sort down, that wins over whatever was clicked here.
    propSortBy(next) {
      if (JSON.stringify(next) !== JSON.stringify(this.internalSortBy)) {
        this.internalSortBy = null
      }
    },
  },
  methods: {
    normalizeSlotProps(slotProps) {
      if (!slotProps || !slotProps.item) return slotProps || {}
      return { ...slotProps, item: slotProps.item.raw || slotProps.item }
    },
    updateSort(sortBy) {
      this.internalSortBy = sortBy || []
      const first = sortBy && sortBy[0]
      this.$emit("update:sortBy", first ? first.key : null)
      this.$emit("update:sortDesc", first ? first.order === "desc" : false)
    },
  },
}
</script>
