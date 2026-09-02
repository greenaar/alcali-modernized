import "material-design-icons-iconfont/dist/material-design-icons.css";
import "typeface-roboto/index.css";
import "vuetify/styles";

import { createVuetify } from "vuetify";
import { aliases, md } from "vuetify/iconsets/md";
import { en, fr } from "vuetify/locale";
import { defaultLocale } from "../i18n/index.js";

// Only `primary` and `secondary` were set before, so every surface fell back to
// Vuetify's stock white/black and the whole application read as flat. These
// define the grounds as well: a page background the cards can sit above, a
// distinct surface for the cards themselves, and a lighter one again for the
// bars and menus that sit above those.
const light = {
  dark: false,
  colors: {
    background: "#f4f5f7",
    surface: "#ffffff",
    "surface-bright": "#ffffff",
    "surface-light": "#eceef1",
    "surface-variant": "#e3e6eb",
    "on-surface-variant": "#43474e",
    primary: "#4f46e5",
    "primary-darken-1": "#4338ca",
    secondary: "#0f766e",
    accent: "#7c3aed",
    error: "#d92d20",
    info: "#0b7285",
    success: "#12805c",
    warning: "#b54708",
  },
};

const dark = {
  dark: true,
  colors: {
    background: "#14161a",
    surface: "#1c1f26",
    "surface-bright": "#2a2f38",
    "surface-light": "#252932",
    "surface-variant": "#343a45",
    "on-surface-variant": "#c3c8d2",
    primary: "#8b93ff",
    "primary-darken-1": "#6f78f5",
    secondary: "#4dd4c0",
    accent: "#c4a7ff",
    error: "#ff6b6b",
    info: "#4dc4e0",
    success: "#3ecf8e",
    warning: "#f5a524",
  },
};

export default createVuetify({
  locale: {
    locale: defaultLocale,
    fallback: "en",
    messages: { en, fr },
  },
  icons: {
    defaultSet: "md",
    aliases,
    sets: { md },
  },
  theme: {
    defaultTheme: "light",
    themes: { light, dark },
    variations: {
      colors: ["primary", "secondary", "error", "success", "warning", "info"],
      lighten: 2,
      darken: 2,
    },
  },
  // Applied to every instance, so the rounding and weight are consistent
  // rather than each call site carrying its own props.
  defaults: {
    VCard: {
      rounded: "lg",
      elevation: 0,
      border: true,
    },
    VBtn: {
      rounded: "lg",
      variant: "flat",
      class: "text-none",
    },
    VTextField: {
      variant: "outlined",
      density: "comfortable",
      rounded: "lg",
    },
    VSelect: {
      variant: "outlined",
      density: "comfortable",
      rounded: "lg",
    },
    VAutocomplete: {
      variant: "outlined",
      density: "comfortable",
      rounded: "lg",
    },
    VCombobox: {
      variant: "outlined",
      density: "comfortable",
      rounded: "lg",
    },
    VChip: {
      rounded: "lg",
      size: "small",
    },
    VAlert: {
      rounded: "lg",
      variant: "tonal",
    },
    VMenu: {
      transition: "fade-transition",
    },
    VDataTable: {
      hover: true,
    },
  },
});
