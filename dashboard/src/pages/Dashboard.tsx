import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { TrendingUp, TrendingDown } from 'lucide-react'

interface MarketSummary {
  symbol: string
  price: number
  timestamp: string
}

async function fetchMarketSummary(): Promise<{ summary: MarketSummary[] }> {
  const res = await fetch('/api/v1/market-summary')
  if (!res.ok) {
    console.error('Market summary fetch failed:', res.status, res.statusText)
    return { summary: [] }
  }
  const data = await res.json()
  console.log('Market data:', data)
  return data
}

export default function Dashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ['market-summary'],
    queryFn: fetchMarketSummary,
  })

  if (isLoading) return <div className="text-center py-8">Loading...</div>

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Market Overview</h1>
      {(!data?.summary || data.summary.length === 0) ? (
        <div className="text-center py-8 text-gray-400">
          <p className="text-xl mb-2">No market data available yet</p>
          <p className="text-sm">Wait for the market simulator to generate data...</p>
        </div>
      ) : (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {data.summary.map((item) => (
          <Link
            key={item.symbol}
            to={`/symbol/${item.symbol}`}
            className="bg-gray-800 rounded-lg p-4 hover:bg-gray-700 transition"
          >
            <div className="font-bold text-lg">{item.symbol}</div>
            <div className="text-2xl font-mono mt-2 flex items-center gap-2">
              ${item.price.toFixed(2)}
              {Math.random() > 0.5 ? (
                <TrendingUp className="w-4 h-4 text-green-400" />
              ) : (
                <TrendingDown className="w-4 h-4 text-red-400" />
              )}
            </div>
          </Link>
        ))}
      </div>
      )}
    </div>
  )
}
