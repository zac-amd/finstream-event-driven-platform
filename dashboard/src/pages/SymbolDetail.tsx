import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

interface YahooQuote {
  symbol: string
  price: number
  open: number
  high: number
  low: number
  volume: number
  previous_close: number
}

interface Candle {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  trade_count: number
}

export default function SymbolDetail() {
  const { symbol } = useParams<{ symbol: string }>()

  // Real-time Yahoo Finance quote - refresh every 5 seconds
  const { data: yahooQuote, isLoading: quoteLoading } = useQuery<YahooQuote>({
    queryKey: ['yahoo-quote', symbol],
    queryFn: async () => {
      const res = await fetch(`/api/v1/yahoo/quote/${symbol}`)
      if (!res.ok) throw new Error('Failed to fetch quote')
      return res.json()
    },
    refetchInterval: 5000, // Refresh every 5 seconds
  })

  // Recent candles from TimescaleDB
  const { data: candlesData } = useQuery({
    queryKey: ['candles', symbol],
    queryFn: () => fetch(`/api/v1/candles/${symbol}?interval=1m&limit=60`).then(r => r.json()),
    refetchInterval: 60000, // Refresh every minute
  })

  // Recent trades
  const { data: tradesData } = useQuery({
    queryKey: ['trades', symbol],
    queryFn: () => fetch(`/api/v1/trades/${symbol}?limit=20`).then(r => r.json()),
    refetchInterval: 5000,
  })

  const priceChange = yahooQuote 
    ? yahooQuote.price - yahooQuote.previous_close 
    : 0
  const priceChangePercent = yahooQuote && yahooQuote.previous_close
    ? ((priceChange / yahooQuote.previous_close) * 100)
    : 0
  const isPositive = priceChange >= 0

  return (
    <div className="space-y-6">
      {/* Header with Symbol and Price */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-gray-400 hover:text-white">← Back</Link>
          <h1 className="text-3xl font-bold">{symbol}</h1>
          <span className="px-2 py-1 bg-blue-600 rounded text-sm">YAHOO</span>
        </div>
        <div className="text-right">
          <div className="text-sm text-gray-400">Last Updated</div>
          <div className="text-sm">{new Date().toLocaleTimeString()}</div>
        </div>
      </div>

      {/* Main Price Card */}
      {quoteLoading ? (
        <div className="bg-gray-800 rounded-lg p-8 text-center">
          <div className="animate-pulse text-gray-400">Loading real-time data...</div>
        </div>
      ) : yahooQuote ? (
        <div className="bg-gray-800 rounded-lg p-6">
          <div className="flex items-baseline gap-4 mb-6">
            <span className="text-5xl font-bold">${yahooQuote.price.toFixed(2)}</span>
            <span className={`text-2xl ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
              {isPositive ? '+' : ''}{priceChange.toFixed(2)} ({priceChangePercent.toFixed(2)}%)
            </span>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <div className="text-gray-400 text-sm">Open</div>
              <div className="text-xl">${yahooQuote.open?.toFixed(2) || 'N/A'}</div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">High</div>
              <div className="text-xl text-green-400">${yahooQuote.high?.toFixed(2) || 'N/A'}</div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Low</div>
              <div className="text-xl text-red-400">${yahooQuote.low?.toFixed(2) || 'N/A'}</div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Previous Close</div>
              <div className="text-xl">${yahooQuote.previous_close?.toFixed(2) || 'N/A'}</div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Volume</div>
              <div className="text-xl">{yahooQuote.volume?.toLocaleString() || 'N/A'}</div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Day Range</div>
              <div className="text-xl">
                ${yahooQuote.low?.toFixed(2)} - ${yahooQuote.high?.toFixed(2)}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-gray-800 rounded-lg p-8 text-center text-red-400">
          Failed to load data for {symbol}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Candles */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-lg font-bold mb-4">1-Minute Candles</h2>
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-gray-800">
                <tr className="text-gray-400 text-left">
                  <th className="p-2">Time</th>
                  <th className="p-2">Open</th>
                  <th className="p-2">High</th>
                  <th className="p-2">Low</th>
                  <th className="p-2">Close</th>
                  <th className="p-2">Vol</th>
                </tr>
              </thead>
              <tbody>
                {candlesData?.candles?.slice(0, 20).map((c: Candle, i: number) => (
                  <tr key={i} className="border-t border-gray-700 hover:bg-gray-700">
                    <td className="p-2">{new Date(c.timestamp).toLocaleTimeString()}</td>
                    <td className="p-2">${Number(c.open).toFixed(2)}</td>
                    <td className="p-2 text-green-400">${Number(c.high).toFixed(2)}</td>
                    <td className="p-2 text-red-400">${Number(c.low).toFixed(2)}</td>
                    <td className="p-2">${Number(c.close).toFixed(2)}</td>
                    <td className="p-2">{c.volume?.toLocaleString()}</td>
                  </tr>
                )) || (
                  <tr>
                    <td colSpan={6} className="p-4 text-center text-gray-400">
                      No candle data yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Trades */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-lg font-bold mb-4">Recent Trades</h2>
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-gray-800">
                <tr className="text-gray-400 text-left">
                  <th className="p-2">Time</th>
                  <th className="p-2">Price</th>
                  <th className="p-2">Quantity</th>
                  <th className="p-2">Side</th>
                </tr>
              </thead>
              <tbody>
                {tradesData?.trades?.map((t: any, i: number) => (
                  <tr key={i} className="border-t border-gray-700 hover:bg-gray-700">
                    <td className="p-2">{new Date(t.timestamp).toLocaleTimeString()}</td>
                    <td className="p-2">${Number(t.price).toFixed(2)}</td>
                    <td className="p-2">{t.quantity?.toLocaleString()}</td>
                    <td className={`p-2 ${t.side === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                      {t.side}
                    </td>
                  </tr>
                )) || (
                  <tr>
                    <td colSpan={4} className="p-4 text-center text-gray-400">
                      No trade data yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-900/30 border border-blue-500/30 rounded-lg p-4 text-sm text-blue-200">
        <strong>Real-time data from Yahoo Finance.</strong> Prices refresh every 5 seconds. 
        Candle data is aggregated from the Kafka stream and stored in TimescaleDB.
      </div>
    </div>
  )
}
