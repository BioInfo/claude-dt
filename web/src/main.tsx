import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import App from "./App";
import Dashboard from "./pages/Dashboard";
import Report from "./pages/Report";
import Recommendations from "./pages/Recommendations";
import Trends from "./pages/Trends";
import Sessions from "./pages/Sessions";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route index element={<Dashboard />} />
          <Route path="report" element={<Report />} />
          <Route path="recommendations" element={<Recommendations />} />
          <Route path="trends" element={<Trends />} />
          <Route path="sessions" element={<Sessions />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>
);
