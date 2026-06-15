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
          bg: '#e8f0f6',
          paper: '#FFFFFF',
          ink: '#172e48',
          muted: '#7f8080',
          subtle: '#b3b4b3',
          border: '#dce2e8',
          borderStr: '#8b97a4',
          accent: '#00588c',
          accentSoft: '#b3d1e5',
          accentBg: '#e6f0f7',
          gold: '#fdc757',
          goldBg: '#fff6e0',
          danger: '#d63b2f',
          dangerBg: '#fae5e3',
          success: '#006833',
          successBg: '#cce1d6',
        },
      },
      fontFamily: {
        display: ["'Manrope'", '-apple-system', 'sans-serif'],
        body: ["'Poppins'", '-apple-system', 'sans-serif'],
        mono: ["'JetBrains Mono'", "'Menlo'", 'monospace'],
      },
    },
  },
  plugins: [],
};
