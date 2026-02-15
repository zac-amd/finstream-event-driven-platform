import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore, authFetch } from '../store/authStore'

interface Holding {
  symbol: string
  quantity: number
  average_cost: number
  total_cost: number
  current_price: number | null
  market_value: number | null
  unrealized_pnl: number | null
  unrealized_pnl_pct: number | null
}

interface PortfolioSummary {
  portfolio_id: string
  name: string
  cash_balance: number
  holdings_value: number
  total_value: number
  total_cost_basis: number
  total_pnl: number
  total_pnl_pct: number
  holdings: Holding[]
}

interface Portfolio {
  id: string
  name: string
  current_cash: number
  is_default: boolean
}

export default function PortfolioPage() {
  const navigate = useNavigate()
  const { isAuthenticated, user, logout } = useAuthStore()
  const [, setPortfolios] = useState<Portfolio[]>([])
  const [selectedPortfolio, setSelectedPortfolio] = useState<string | null>(null)
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [tradeModal, setTradeModal] = useState<{ type: 'buy' | 'sell'; symbol?: string } | null>(null)
  const [tradeForm, setTradeForm] = useState({ symbol: '', quantity: '' })
  const [tradeLoading, setTradeLoading] = useState(false)
  const [tradeError, setTradeError] = useState('')

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login')
      return
    }
    loadPortfolios()
  }, [isAuthenticated])

  useEffect(() => {
    if (selectedPortfolio) {
      loadSummary()
    }
  }, [selectedPortfolio])

  const loadPortfolios = async () => {
    const res = await authFetch('/api/v1/portfolios')
    if (res.ok) {
      const data = await res.json()
      setPortfolios(data)
      if (data.length > 0) {
        setSelectedPortfolio(data[0].id)
      }
    }
    setLoading(false)
  }

  const loadSummary = async () => {
    if (!selectedPortfolio) return
    const res = await authFetch(`/api/v1/portfolios/${selectedPortfolio}/summary`)
    if (res.ok) {
      setSummary(await res.json())
    }
  }

  const handleTrade = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedPortfolio || !tradeModal) return
    
    setTradeLoading(true)
    setTradeError('')

    try {
      const endpoint = tradeModal.type === 'buy' ? 'buy' : 'sell'
      const res = await authFetch(`/api/v1/portfolios/${selectedPortfolio}/${endpoint}`, {
        method: 'POST',
        body: JSON.stringify({
          symbol: tradeForm.symbol.toUpperCase(),
          quantity: parseFloat(tradeForm.quantity),
        }),
      })

      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Trade failed')
      }

      setTradeModal(null)
      setTradeForm({ symbol: '', quantity: '' })
      loadSummary()
    } catch (err) {
      setTradeError(err instanceof Error ? err.message : 'Trade failed')
    } finally {
      setTradeLoading(false)
    }
  }

  const openSellModal = (symbol: string) => {
    setTradeForm({ symbol, quantity: '' })
    setTradeModal({ type: 'sell', symbol })
  }

  if (!isAuthenticated) return null
  if (loading) return <div className="p-6 text-white">Loading...</div>

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center space-x-6">
            <Link to="/" className="text-xl font-bold text-blue-400">FinStream</Link>
            <nav className="flex space-x-4">
              <Link to="/" className="text-gray-400 hover:text-white">Market</Link>
              <Link to="/portfolio" className="text-white">Portfolio</Link>
              <Link to="/leaderboard" className="text-gray-400 hover:text-white">Leaderboard</Link>
            </nav>
          </div>
          <div className="flex items-center space-x-4">
            <span className="text-gray-400">@{user?.username}</span>
            <button onClick={logout} className="text-gray-400 hover:text-white">Logout</button>
          </div>
        </div>
      </header>

      <div className="p-6">
        {/* Portfolio Summary */}
        {summary && (
          <>
            <div className="grid grid-cols-5 gap-4 mb-6">
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="text-gray-400 text-sm">Total Value</div>
                <div className="text-2xl font-bold">${summary.total_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="text-gray-400 text-sm">Cash Balance</div>
                <div className="text-2xl font-bold">${summary.cash_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="text-gray-400 text-sm">Holdings Value</div>
                <div className="text-2xl font-bold">${summary.holdings_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="text-gray-400 text-sm">Total P&L</div>
                <div className={`text-2xl font-bold ${summary.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {summary.total_pnl >= 0 ? '+' : ''}${summary.total_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="text-gray-400 text-sm">Return %</div>
                <div className={`text-2xl font-bold ${summary.total_pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {summary.total_pnl_pct >= 0 ? '+' : ''}{summary.total_pnl_pct.toFixed(2)}%
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold">Holdings</h2>
              <div className="flex space-x-2">
                <button
                  onClick={() => { setTradeForm({ symbol: '', quantity: '' }); setTradeModal({ type: 'buy' }) }}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded font-semibold"
                >
                  Buy Stock
                </button>
                <Link to={`/transactions/${selectedPortfolio}`} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded">
                  Transaction History
                </Link>
              </div>
            </div>

            {/* Holdings Table */}
            <div className="bg-gray-800 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-700">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-semibold">Symbol</th>
                    <th className="px-4 py-3 text-right text-sm font-semibold">Qty</th>
                    <th className="px-4 py-3 text-right text-sm font-semibold">Avg Cost</th>
                    <th className="px-4 py-3 text-right text-sm font-semibold">Current</th>
                    <th className="px-4 py-3 text-right text-sm font-semibold">Market Value</th>
                    <th className="px-4 py-3 text-right text-sm font-semibold">P&L</th>
                    <th className="px-4 py-3 text-right text-sm font-semibold">P&L %</th>
                    <th className="px-4 py-3 text-right text-sm font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.holdings.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                        No holdings yet. Buy your first stock!
                      </td>
                    </tr>
                  ) : (
                    summary.holdings.map((h) => (
                      <tr key={h.symbol} className="border-t border-gray-700 hover:bg-gray-700/50">
                        <td className="px-4 py-3">
                          <Link to={`/symbol/${h.symbol}`} className="text-blue-400 hover:underline font-medium">
                            {h.symbol}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-right">{h.quantity}</td>
                        <td className="px-4 py-3 text-right">${h.average_cost?.toFixed(2)}</td>
                        <td className="px-4 py-3 text-right">${h.current_price?.toFixed(2) || '-'}</td>
                        <td className="px-4 py-3 text-right">${h.market_value?.toFixed(2) || '-'}</td>
                        <td className={`px-4 py-3 text-right ${(h.unrealized_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {(h.unrealized_pnl ?? 0) >= 0 ? '+' : ''}${h.unrealized_pnl?.toFixed(2) || '0.00'}
                        </td>
                        <td className={`px-4 py-3 text-right ${(h.unrealized_pnl_pct ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {(h.unrealized_pnl_pct ?? 0) >= 0 ? '+' : ''}{h.unrealized_pnl_pct?.toFixed(2) || '0.00'}%
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => openSellModal(h.symbol)}
                            className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm"
                          >
                            Sell
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {/* Trade Modal */}
      {tradeModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-xl font-bold mb-4">
              {tradeModal.type === 'buy' ? 'Buy Stock' : `Sell ${tradeModal.symbol}`}
            </h3>
            
            {tradeError && (
              <div className="bg-red-900/50 border border-red-500 text-red-200 px-4 py-3 rounded mb-4">
                {tradeError}
              </div>
            )}

            <form onSubmit={handleTrade} className="space-y-4">
              {tradeModal.type === 'buy' && (
                <div>
                  <label className="block text-gray-400 text-sm mb-1">Symbol</label>
                  <input
                    type="text"
                    required
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded text-white uppercase"
                    value={tradeForm.symbol}
                    onChange={(e) => setTradeForm({ ...tradeForm, symbol: e.target.value.toUpperCase() })}
                    placeholder="e.g. AAPL"
                  />
                </div>
              )}
              <div>
                <label className="block text-gray-400 text-sm mb-1">Quantity</label>
                <input
                  type="number"
                  required
                  min="1"
                  step="1"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                  value={tradeForm.quantity}
                  onChange={(e) => setTradeForm({ ...tradeForm, quantity: e.target.value })}
                />
              </div>
              <div className="flex space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => { setTradeModal(null); setTradeError('') }}
                  className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 rounded"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={tradeLoading}
                  className={`flex-1 py-2 rounded font-semibold ${
                    tradeModal.type === 'buy'
                      ? 'bg-green-600 hover:bg-green-700'
                      : 'bg-red-600 hover:bg-red-700'
                  }`}
                >
                  {tradeLoading ? 'Processing...' : tradeModal.type === 'buy' ? 'Buy' : 'Sell'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
