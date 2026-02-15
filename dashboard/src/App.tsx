import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import SymbolDetail from './pages/SymbolDetail'
import Alerts from './pages/Alerts'
import Login from './pages/Login'
import Portfolio from './pages/Portfolio'
import Leaderboard from './pages/Leaderboard'
import Layout from './components/Layout'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Auth routes - no layout */}
        <Route path="/login" element={<Login />} />
        
        {/* Portfolio routes - own layout */}
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/leaderboard" element={<Leaderboard />} />
        
        {/* Market data routes - with layout */}
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="symbol/:symbol" element={<SymbolDetail />} />
          <Route path="alerts" element={<Alerts />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
