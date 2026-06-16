/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        title: ['"Baloo Tamma 2"', "system-ui", "sans-serif"],
      },
      colors: {
        moony: {
          bg: "#0a0a0f",
          panel: "#12121a",
          accent: "#7c6cff",
          glow: "#a78bfa",
        },
      },
    },
  },
  plugins: [],
};
