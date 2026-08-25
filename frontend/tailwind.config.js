/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    // The design system in `src/styles/industry.css` is the source of truth
    // for the look (it is lifted from the approved wireframe). Tailwind is
    // here for one-off layout utilities only, so its scales are re-pointed at
    // the same custom properties rather than shipping a second, conflicting
    // palette.
    extend: {
      colors: {
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        ink: "var(--color-text)",
        accent: "var(--color-accent)",
        divider: "var(--color-divider)",
      },
      fontFamily: {
        heading: ["var(--font-heading)"],
        body: ["var(--font-body)"],
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
      },
    },
  },
  plugins: [],
};
