import React from "react";
import { createRoot } from "react-dom/client";
import { AuthGate } from "./Auth.jsx";
import { Shell } from "./Shell.jsx";
import "./app.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AuthGate>
      <Shell />
    </AuthGate>
  </React.StrictMode>,
);
