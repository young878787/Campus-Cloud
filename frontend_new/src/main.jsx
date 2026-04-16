import React from "react";
import ReactDOM from "react-dom/client";
import "@material-design-icons/font/outlined.css";
import App from "./App";
import { ThemeProvider } from "./contexts/ThemeContext";
import { AuthProvider }  from "./contexts/AuthContext";
import "./assets/styles/global.scss";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <App />
      </AuthProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
