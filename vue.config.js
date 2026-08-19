const { VuetifyPlugin } = require("webpack-plugin-vuetify");

module.exports = {
  productionSourceMap: false,
  outputDir: "dist",
  assetsDir: "static",
  configureWebpack: {
    plugins: [new VuetifyPlugin({ autoImport: true })],
  },
  devServer: {
    proxy: {
      "/api*": {
        // Forward frontend dev server request for /api to django dev server
        target: "http://localhost:8000/",
      },
    },
  },
};
