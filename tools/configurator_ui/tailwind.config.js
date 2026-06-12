/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  // Scope every utility to the embed root so styles can't leak into a Webflow
  // host page, and so our utilities win against the host's own CSS.
  important: '#ill-configurator-root',
  // Disable Tailwind's global Preflight reset (it would restyle the whole host
  // page). Scoped resets live in index.css under #ill-configurator-root.
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        ill: {
          bg: '#FAF7F2',
          paper: '#FFFFFF',
          ink: '#1A1612',
          muted: '#6B5F52',
          subtle: '#938676',
          border: '#E8E1D4',
          borderStr: '#D4CBB8',
          accent: '#B45309',
          accentSoft: '#F3E5C7',
          accentBg: '#FDF4E2',
          danger: '#9B2C2C',
          dangerBg: '#FBEDED',
          success: '#3F6D48',
          successBg: '#ECF3ED',
        },
      },
      fontFamily: {
        display: ["'Fraunces'", "'Georgia'", 'serif'],
        body: ["'Work Sans'", '-apple-system', 'sans-serif'],
        mono: ["'JetBrains Mono'", "'Menlo'", 'monospace'],
      },
    },
  },
  plugins: [],
};
