/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef7f1", 100: "#d6ecdf", 200: "#aedac0", 300: "#7fc39c",
          400: "#4fa877", 500: "#2f8c5c", 600: "#217049", 700: "#1b5a3b",
          800: "#164830", 900: "#123a27",
        },
      },
    },
  },
  plugins: [],
}
