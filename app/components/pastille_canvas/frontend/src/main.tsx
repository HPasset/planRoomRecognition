import React from "react";
import ReactDOM from "react-dom/client";
import PastilleCanvas from "./PastilleCanvas";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PastilleCanvas />
  </React.StrictMode>,
);
