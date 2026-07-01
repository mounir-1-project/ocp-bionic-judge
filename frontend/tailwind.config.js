/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{jsx,tsx,js,ts}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        bg:      '#0C0E14',
        surf:    '#141622',
        card:    '#1E2130',
        'card-hv': '#242840',
        border:  '#252840',
        border2: '#353A52',
        green:   '#00D37F',
        'green-d': '#00A362',
        'green-l': '#4DFFA9',
        amber:   '#FFB020',
        danger:  '#F04438',
        blue:    '#4F7CF6',
        teal:    '#06B6D4',
        text1:   '#E8ECF1',
        text2:   '#8B92A9',
        text3:   '#525870',
      },
    },
  },
}
