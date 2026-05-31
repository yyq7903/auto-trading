import React from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider, theme } from "antd";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <ConfigProvider
    theme={{
      algorithm: theme.darkAlgorithm,
      token: {
        colorPrimary: "#8b5cf6",
        colorBgContainer: "#121726",
        colorBgElevated: "#181f35",
        colorBorderSecondary: "#232d4a",
        colorText: "#e8ecf8",
        colorTextSecondary: "#6b7a9e",
        colorTextTertiary: "#4a5568",
        colorSuccess: "#22c55e",
        colorError: "#ef4444",
        colorWarning: "#f59e0b",
        borderRadius: 6,
        fontFamily: "Inter, system-ui, sans-serif",
      },
    }}
  >
    <App />
  </ConfigProvider>
);
