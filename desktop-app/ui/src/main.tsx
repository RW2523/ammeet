import React from "react";
import ReactDOM from "react-dom/client";
import App, { whichWindow } from "./App";
import "./styles.css";

// The overlay window needs a fully transparent page; settings gets the solid
// slate background. Applied before first paint via a body class.
document.body.classList.add(`win-${whichWindow()}`);

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
