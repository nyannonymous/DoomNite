/** @type {import('tailwindcss').Config} */
export default {
  // Tailwind v3 explicit content list. Without this the JIT scans nothing and
  // every class below this file comes out as dead CSS.
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Gunmetal: the structural greys. Not flat -- these are all used under
        // a noise overlay and a bevel, never as a plain fill.
        gunmetal: {
          900: "#08090b",
          800: "#0e1013",
          700: "#16191d",
          600: "#1e2227",
          500: "#2a2f36",
          400: "#3a4149",
          300: "#525a64",
          200: "#7c848e",
          100: "#aeb5bd",
          50: "#d8dce1",
        },
        // Industrial rust: oxidised metal, accents and the "aged" panels.
        rust: {
          600: "#7a3b18",
          500: "#a5521f",
          400: "#c76a2c",
          300: "#e08a45",
          200: "#f0aa6b",
        },
        // Toxic green: reserved for "armed / ready / will launch". Using it
        // for anything decorative would dilute the one colour that matters.
        toxic: {
          600: "#3d6b1f",
          500: "#5b942e",
          400: "#7fc23c",
          300: "#a3e05c",
          200: "#c9f58c",
        },
        // Blood: the act of launching, and errors. Never decoration.
        blood: {
          700: "#6b0f14",
          600: "#8c1418",
          500: "#b71c1c",
          400: "#e02f2f",
          300: "#ff5c5c",
          200: "#ff9a9a",
        },
      },
      fontFamily: {
        // Chunky industrial for headers.
        display: ["'Black Ops One'", "Oswald", "Impact", "sans-serif"],
        // Slightly condensed industrial, for labels and buttons.
        head: ["Oswald", "'Arial Narrow'", "sans-serif"],
        // Clean monospace for the terminal readout.
        mono: ["'JetBrains Mono'", "'Fira Code'", "Consolas", "monospace"],
      },
      letterSpacing: {
        // Doom's UI reads as shouted. Wide tracking does a lot of that work.
        doom: "0.14em",
        wider2: "0.22em",
      },
      boxShadow: {
        // Bevels: a light top edge and a dark bottom edge read as raised metal.
        bevel: "inset 0 1px 0 rgba(255,255,255,0.09), inset 0 -1px 0 rgba(0,0,0,0.6)",
        "bevel-sm": "inset 0 1px 0 rgba(255,255,255,0.06), inset 0 -1px 0 rgba(0,0,0,0.5)",
        inset: "inset 0 2px 8px rgba(0,0,0,0.85)",
        "glow-toxic": "0 0 24px -4px rgba(127,194,60,0.75)",
        "glow-blood": "0 0 28px -4px rgba(224,47,47,0.8)",
        "glow-rust": "0 0 30px -6px rgba(199,106,44,0.7)",
      },
      backdropBlur: {
        uac: "2px",
      },
      transitionTimingFunction: {
        // UAC panels snap. Not bounce, not ease -- a fast mechanical slide.
        uac: "cubic-bezier(0.16, 1, 0.3, 1)",
        jolt: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
      keyframes: {
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
        flicker: {
          "0%,100%": { opacity: "1" },
          "92%": { opacity: "1" },
          "93%": { opacity: "0.55" },
          "94%": { opacity: "1" },
          "96%": { opacity: "0.7" },
          "97%": { opacity: "1" },
        },
        glitchx: {
          "0%,100%": { transform: "translate(0)" },
          "20%": { transform: "translate(-2px, 1px)" },
          "40%": { transform: "translate(2px, -1px)" },
          "60%": { transform: "translate(-1px, -1px)" },
          "80%": { transform: "translate(1px, 1px)" },
        },
      },
      animation: {
        scan: "scan 7s linear infinite",
        flicker: "flicker 6s steps(1) infinite",
        glitchx: "glitchx 0.28s steps(2) infinite",
      },
    },
  },
  plugins: [],
};