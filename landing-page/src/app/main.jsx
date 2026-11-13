import React from "react";
import { createRoot } from "react-dom/client";
import { Shell } from "./Shell.jsx";
import "./app.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Shell />
  </React.StrictMode>,
);
