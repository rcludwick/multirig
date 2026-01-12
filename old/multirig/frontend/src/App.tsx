import { Routes, Route } from 'react-router-dom';
import { useEffect } from 'react';
import TopBar from './components/layout/TopBar';
import PageNav from './components/layout/PageNav';
import Footer from './components/layout/Footer';
import { Dashboard, Settings } from './pages';
import { useWebSocket } from './hooks/useWebSocket';
import { useConfigStore } from './stores/configStore';

function App() {
  const { loadRigModels, loadConfig } = useConfigStore();

  // Connect WebSocket for real-time updates
  useWebSocket();

  // Load initial data
  useEffect(() => {
    loadRigModels();
    loadConfig();
  }, [loadRigModels, loadConfig]);

  return (
    <div className="app">
      <TopBar />
      <PageNav />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}

export default App;
