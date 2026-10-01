import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

// Self-hosted via @fontsource. This app runs off a local Python server on the
// user's own machine, frequently with no internet, so a Google Fonts <link>
// would silently fall back to a system font and lose the whole aesthetic.
import "@fontsource/black-ops-one/400.css";
import "@fontsource/oswald/500.css";
import "@fontsource/oswald/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/700.css";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);