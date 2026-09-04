/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: '#0F2A44', 700: '#0B2036', 600: '#163A5C', 100: '#E3EAF2', 50: '#F2F5F8' },
        teal: { DEFAULT: '#1B7F79', 700: '#15655F', 100: '#DDEFEE', 50: '#EEF7F6' },
        sev: { critical: '#B03A2E', high: '#D9822B', medium: '#C9A227', low: '#2A78D6', info: '#6B7280' },
        ok: '#1F7A3A',
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: { xxs: ['11px', '14px'] },
    },
  },
  plugins: [],
};
