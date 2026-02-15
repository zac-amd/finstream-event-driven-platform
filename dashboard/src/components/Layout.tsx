import { Outlet, Link } from 'react-router-dom'
import { TrendingUp, Bell, BarChart3 } from 'lucide-react'

export default function Layout() {
  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <nav className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-xl font-bold text-green-400">
            <TrendingUp className="w-6 h-6" />
            FinStream
          </Link>
          <div className="flex gap-4">
            <Link to="/" className="flex items-center gap-1 hover:text-green-400">
              <BarChart3 className="w-4 h-4" /> Dashboard
            </Link>
            <Link to="/alerts" className="flex items-center gap-1 hover:text-green-400">
              <Bell className="w-4 h-4" /> Alerts
            </Link>
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
