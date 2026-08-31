import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'emerald-online': '#10b981',
        'amber-suspect': '#f59e0b',
        'crimson-alert': '#ef4444',
        'cyan-telemetry': '#06b6d4',
        'tactical-dark': '#0a0e17',
        'tactical-panel': '#0f172a',
      },
    },
  },
  plugins: [],
}
export default config
