import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import RequirementPage from './pages/RequirementPage';
import GraphPage from './pages/GraphPage';
import HistoryPage from './pages/HistoryPage';
import ObservabilityPage from './pages/ObservabilityPage';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/requirement" replace />} />
        <Route path="/requirement" element={<RequirementPage />} />
        <Route path="/graph" element={<GraphPage />} />
        {/* legacy /hitl redirects to requirement (HITL UX is inline there now). */}
        <Route path="/hitl" element={<Navigate to="/requirement" replace />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/observability" element={<ObservabilityPage />} />
      </Routes>
    </Layout>
  );
}
