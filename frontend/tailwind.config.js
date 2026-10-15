/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        govblue: {
          50: '#f0f5fa',
          100: '#e1ecf5',
          600: '#1e40af',
          700: '#1d4ed8',
          800: '#1e3a8a',
          900: '#0f172a'
        },
        govemerald: {
          600: '#059669',
          700: '#047857'
        }
      },
      fontFamily: {
        sans: ['Inter', 'Noto Sans Telugu', 'system-ui', 'sans-serif'],
        telugu: ['Noto Sans Telugu', 'sans-serif']
      }
    },
  },
  plugins: [],
}
