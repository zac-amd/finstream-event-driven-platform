import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

interface LeaderboardEntry {
  portfolio_id: string
  portfolio_name: string
  username: string
  total_value: number
  initial_value: number
  return_pct: number
}

export default function Leaderboard() {
  const { isAuthenticated, user, logout } = useAuthStore()
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadLeaderboard()
  }, [])

  const loadLeaderboard = async () => {
    try {
      const res = await fetch('/api/v1/leaderboard?limit=20')
      if (res.ok) {
        setEntries(await res.json())
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center space-x-6">
            <Link to="/" className="text-xl font-bold text-blue-400">FinStream</Link>
            <nav className="flex space-x-4">
              <Link to="/" className="text-gray-400 hover:text-white">Market</Link>
              <Link to="/portfolio" className="text-gray-400 hover:text-white">Portfolio</Link>
              <Link to="/leaderboard" className="text-white">Leaderboard</Link>
            </nav>
          </div>
          <div className="flex items-center space-x-4">
            {isAuthenticated ? (
              <>
                <span className="text-gray-400">@{user?.username}</span>
                <button onClick={logout} className="text-gray-400 hover:text-white">Logout</button>
              </>
            ) : (
              <Link to="/login" className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded">
                Sign In
              </Link>
            )}
          </div>
        </div>
      </header>

      <div className="p-6">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold">🏆 Public Leaderboard</h1>
          <p className="text-gray-400">Top performing public portfolios</p>
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-400">Loading...</div>
        ) : entries.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-gray-400 mb-4">No public portfolios yet</div>
            <Link to="/login" className="text-blue-400 hover:underline">
              Create an account and make your portfolio public to compete!
            </Link>
          </div>
        ) : (
          <div className="bg-gray-800 rounded-lg overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-700">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Rank</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Trader</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Portfolio</th>
                  <th className="px-4 py-3 text-right text-sm font-semibold">Total Value</th>
                  <th className="px-4 py-3 text-right text-sm font-semibold">Starting Capital</th>
                  <th className="px-4 py-3 text-right text-sm font-semibold">Return %</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry, index) => (
                  <tr key={entry.portfolio_id} className="border-t border-gray-700 hover:bg-gray-700/50">
                    <td className="px-4 py-4">
                      <span className={`text-lg font-bold ${
                        index === 0 ? 'text-yellow-400' :
                        index === 1 ? 'text-gray-300' :
                        index === 2 ? 'text-amber-600' : 'text-gray-400'
                      }`}>
                        {index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : `#${index + 1}`}
                      </span>
                    </td>
                    <td className="px-4 py-4">
                      <span className="font-medium">@{entry.username}</span>
                    </td>
                    <td className="px-4 py-4 text-gray-400">{entry.portfolio_name}</td>
                    <td className="px-4 py-4 text-right font-mono">
                      ${entry.total_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="px-4 py-4 text-right text-gray-400 font-mono">
                      ${entry.initial_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className={`px-4 py-4 text-right font-bold ${
                      entry.return_pct >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {entry.return_pct >= 0 ? '+' : ''}{entry.return_pct.toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-8 bg-gray-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-3">How to join the leaderboard</h2>
          <ol className="list-decimal list-inside space-y-2 text-gray-400">
            <li>Create an account or sign in</li>
            <li>Start trading with your $10,000 virtual cash</li>
            <li>Go to Portfolio Settings and enable "Make portfolio public"</li>
            <li>Your portfolio will appear here ranked by total value</li>
          </ol>
        </div>
      </div>
    </div>
  )
}
