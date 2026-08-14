/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
          wash: "hsl(var(--accent-wash))",
        },
        /* The identity itself, for the logo lockup and brand moments.
           `ink` flips with the theme so the wordmark stays legible. */
        brand: {
          ink: "hsl(var(--brand-ink))",
          accent: "hsl(var(--brand-accent))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar))",
          foreground: "hsl(var(--sidebar-foreground))",
          border: "hsl(var(--sidebar-border))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          mark: "hsl(var(--sidebar-mark))",
        },
        /* Sunken ground for tables, insets and technical data. */
        well: {
          DEFAULT: "hsl(var(--well))",
          foreground: "hsl(var(--well-foreground))",
        },
        /* The heavier of the two rule weights. */
        "border-strong": "hsl(var(--border-strong))",
        /* Site-convention state colours, plus their tinted grounds. */
        state: {
          verified: "hsl(var(--state-verified))",
          progress: "hsl(var(--state-progress))",
          review: "hsl(var(--state-review))",
          overdue: "hsl(var(--state-overdue))",
          blocked: "hsl(var(--state-blocked))",
          idle: "hsl(var(--state-idle))",
        },
        wash: {
          verified: "hsl(var(--state-verified-wash))",
          progress: "hsl(var(--state-progress-wash))",
          review: "hsl(var(--state-review-wash))",
          overdue: "hsl(var(--state-overdue-wash))",
          blocked: "hsl(var(--state-blocked-wash))",
          idle: "hsl(var(--state-idle-wash))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        chip: "var(--radius-chip)",
        control: "var(--radius-control)",
        panel: "var(--radius-panel)",
        sheet: "var(--radius-sheet)",
      },
      boxShadow: {
        sheet: "var(--shadow-sheet)",
        lift: "var(--shadow-lift)",
        float: "var(--shadow-float)",
      },
      letterSpacing: {
        display: "var(--tracking-display)",
        heading: "var(--tracking-heading)",
        label: "var(--tracking-label)",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        arabic: ["Cairo", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      keyframes: {
        "slide-in-right": {
          "0%": { transform: "translateX(100%)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
        "slide-out-right": {
          "0%": { transform: "translateX(0)", opacity: "1" },
          "100%": { transform: "translateX(100%)", opacity: "0" },
        },
        "slide-in-left": {
          "0%": { transform: "translateX(-100%)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "scale-in": {
          "0%": { transform: "scale(0.95)", opacity: "0" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
        "rise-in": {
          "0%": { transform: "translateY(4px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        "draw-in": {
          "0%": { "stroke-dashoffset": "1" },
          "100%": { "stroke-dashoffset": "0" },
        },
      },
      animation: {
        "slide-in-right": "slide-in-right 0.3s ease-out",
        "slide-out-right": "slide-out-right 0.3s ease-in",
        "slide-in-left": "slide-in-left 0.3s ease-out",
        "fade-in": "fade-in 0.2s ease-out",
        "scale-in": "scale-in 0.2s ease-out",
        "rise-in": "rise-in 0.28s cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [],
};
