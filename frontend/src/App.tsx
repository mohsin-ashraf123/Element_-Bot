import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "./lib/theme";
import { AuthProvider } from "./lib/auth";
import { IconSprite } from "./components/Icon";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { AppLayout } from "./components/layout/AppLayout";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Team } from "./pages/Team";
import { History } from "./pages/History";
import { Performance } from "./pages/Performance";
import { Reports } from "./pages/Reports";
import { Room } from "./pages/Room";
import { Schedule } from "./pages/Schedule";
import { Jobs } from "./pages/Jobs";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <IconSprite />
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route index element={<Dashboard />} />
                <Route path="team" element={<Team />} />
                <Route path="history" element={<History />} />
                <Route path="performance" element={<Performance />} />
                <Route path="reports" element={<Reports />} />
                <Route path="room" element={<Room />} />
                <Route path="schedule" element={<Schedule />} />
                <Route path="jobs" element={<Jobs />} />
                <Route path="settings" element={<Settings />} />
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
