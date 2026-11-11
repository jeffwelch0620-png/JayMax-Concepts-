// Unit tests (replaces Create React App's built-in Jest setup, 2026-11-11), with its defaults:
// jsdom, tests under src/, mocks reset before every test, CSS imports stubbed.
module.exports = {
  roots: ["<rootDir>/src"],
  testEnvironment: "jsdom",
  testMatch: ["<rootDir>/src/**/*.{spec,test}.{js,jsx}"],
  transform: { "^.+\\.(js|jsx|mjs|cjs)$": "babel-jest" },
  transformIgnorePatterns: ["[/\\\\]node_modules[/\\\\].+\\.(js|jsx|mjs|cjs)$"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
    "\\.(css|less|scss|sass)$": "<rootDir>/jest/styleStub.js",
  },
  resetMocks: true,
};
