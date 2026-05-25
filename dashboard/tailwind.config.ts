import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          bg: "#0a0a0f",
          card: "#12121a",
          border: "#1e1e2e",
        },
        text: {
          primary: "#e4e4e7",
          muted: "#71717a",
        },
        danger: "#ef4444",
        warning: "#f59e0b",
        safe: "#22c55e",
        info: "#3b82f6",
      },
      fontFamily: {
        mono: ["var(--font-jetbrains)", "JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
