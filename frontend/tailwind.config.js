/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Medical-tech palette: deep teal + slate, high contrast text.
        brand: {
          50: '#eefcfb',
          100: '#d3f6f5',
          200: '#a9ecec',
          300: '#71dcdd',
          400: '#35c3c7',
          500: '#17a6ac',
          600: '#0f8489',
          700: '#106a6f',
          800: '#12555a',
          900: '#13474b',
        },
        risk: {
          low: '#0f766e',
          lowBg: '#ecfdf5',
          high: '#b91c1c',
          highBg: '#fef2f2',
        },
      },
      fontFamily: {
        sans: [
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Noto Sans SC',
          'Microsoft YaHei',
          'sans-serif',
        ],
      },
      boxShadow: {
        card: '0 1px 2px rgba(15, 23, 42, 0.06), 0 8px 24px -12px rgba(15, 23, 42, 0.18)',
      },
      keyframes: {
        'fade-in': { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 200ms ease-out',
        'slide-up': 'slide-up 240ms ease-out',
      },
    },
  },
  plugins: [],
};
