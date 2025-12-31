/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Knowledge Archive dark theme with golden glow
        // Primary: Deep dark backgrounds
        dark: {
          DEFAULT: '#0a0a0f',
          50: '#18181f',
          100: '#1a1a24',
          200: '#1f1f2e',
          300: '#252538',
          400: '#2d2d42',
          500: '#36364d',
          600: '#404058',
          700: '#4a4a63',
          800: '#55556e',
          900: '#606079',
        },
        // Rich golden accent - warm, luxurious gold tones
        gold: {
          DEFAULT: '#D4AF37',
          50: '#FDF8E8',
          100: '#F9EEC8',
          200: '#F5E4A0',
          300: '#E8D170',
          400: '#DBBD4A',
          500: '#D4AF37',
          600: '#B8960F',
          700: '#96780A',
          800: '#745C08',
          900: '#524106',
          glow: 'rgba(212, 175, 55, 0.45)',
          'glow-strong': 'rgba(212, 175, 55, 0.65)',
        },
        // Telegram theme colors via CSS variables (fallback to dark theme)
        tg: {
          bg: 'var(--tg-theme-bg-color, #0a0a0f)',
          text: 'var(--tg-theme-text-color, #e5e5e5)',
          hint: 'var(--tg-theme-hint-color, #6b7280)',
          link: 'var(--tg-theme-link-color, #DBBD4A)',
          button: 'var(--tg-theme-button-color, #D4AF37)',
          'button-text': 'var(--tg-theme-button-text-color, #0a0a0f)',
          secondary: 'var(--tg-theme-secondary-bg-color, #1a1a24)',
          header: 'var(--tg-theme-header-bg-color, #0a0a0f)',
          accent: 'var(--tg-theme-accent-text-color, #DBBD4A)',
          section: 'var(--tg-theme-section-bg-color, #1f1f2e)',
          'section-header': 'var(--tg-theme-section-header-text-color, #9ca3af)',
          subtitle: 'var(--tg-theme-subtitle-text-color, #6b7280)',
          destructive: 'var(--tg-theme-destructive-text-color, #ef4444)',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
        serif: ['Georgia', 'Cambria', 'Times New Roman', 'Times', 'serif'],
      },
      boxShadow: {
        'gold-glow': '0 0 20px rgba(212, 175, 55, 0.35)',
        'gold-glow-lg': '0 0 40px rgba(212, 175, 55, 0.45)',
        'gold-glow-sm': '0 0 10px rgba(212, 175, 55, 0.25)',
        'gold-inner': 'inset 0 1px 0 rgba(255, 255, 255, 0.1), 0 0 20px rgba(212, 175, 55, 0.35)',
      },
      animation: {
        'glow-pulse': 'glow-pulse 2.5s ease-in-out infinite',
        'shimmer': 'shimmer 2s linear infinite',
      },
      keyframes: {
        'glow-pulse': {
          '0%, 100%': { boxShadow: '0 0 20px rgba(212, 175, 55, 0.35)' },
          '50%': { boxShadow: '0 0 35px rgba(212, 175, 55, 0.55)' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
    },
  },
  plugins: [],
}
