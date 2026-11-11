// Used by Jest only; Vite compiles the app itself. JSX uses the automatic runtime, as under Create React App.
module.exports = {
  presets: [
    ["@babel/preset-env", { targets: { node: "current" } }],
    ["@babel/preset-react", { runtime: "automatic" }],
  ],
};
