import "material-design-icons-iconfont/dist/material-design-icons.css";
import "typeface-roboto/index.css";
import "vuetify/styles";

import { createVuetify } from "vuetify";
import { aliases, md } from "vuetify/iconsets/md";
import { en, fr } from "vuetify/locale";
import { defaultLocale } from "../i18n/index.js";

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
    themes: {
      light: {
        dark: false,
        colors: { primary: "#6200EE", secondary: "#03DAC6" },
      },
      dark: {
        dark: true,
        colors: { primary: "#03DAC6", secondary: "#BB86FC" },
      },
    },
  },
});
