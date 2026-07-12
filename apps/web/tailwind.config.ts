import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        graphite: {
          50: "#f6f6f7",
          100: "#e2e3e5",
          500: "#636574",
          800: "#373942",
          950: "#1b1c21",
        },
        signal: {
          lime: "#d8ff6d",
          coral: "#ff7a59",
          teal: "#1f5965",
        },
      },
      fontFamily: {
        sans: ["Inter", "SF Pro Display", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "SF Mono", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
