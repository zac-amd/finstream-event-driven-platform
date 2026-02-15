import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

export default function SymbolDetail() {
  const { symbol } = useParams<{ symbol: string }>()

  const { data: quote } = useQuery({
    queryKey: ['quote', symbol],
    queryFn: () => fetch(`/api/v1/quotes/${symbol}`).then(r => r.json()),
  })

  const { data: candles } = useQuery({
    queryKey: ['candles', symbol],
    queryFn: () => fetch(`/api/v1/candles/${symbol}?interval=1m&limit=60`).then(r => r.json()),
  })

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">{symbol}</h1>
      {quote && (
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <div className="grid grid-cols-2 gap-4">
            <div><span className="text-gray-400">Bid:</span> ${quote.bid_price}</div>
            <div><span className="text-gray-400">Ask:</span> ${quote.ask_price}</div>
            <div><span className="text-gray-400">Spread:</span> ${(quote.ask_price - quote.bid_price).toFixed(4)}</div>
            <div><span className="text-gray-400">Exchange:</span> {quote.exchange}</div>
          </div>
        </div>
      )}
      <div className="bg-gray-800 rounded-lg p-6">
        <h2 className="text-lg font-bold mb-4">Recent Candles (1m)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-gray-400 text-left">
              <th className="p-2">Time</th><th className="p-2">Open</th><th className="p-2">High</th>
              <th className="p-2">Low</th><th className="p-2">Close</th><th className="p-2">Volume</th>
            </tr></thead>
            <tbody>
              {candles?.candles?.slice(0, 10).map((c: any, i: number) => (
                <tr key={i} className="border-t border-gray-700">
                  <td className="p-2">{new Date(c.timestamp).toLocaleTimeString()}</td>
                  <td className="p-2">${c.open}</td><td className="p-2 text-green-400">${c.high}</td>
                  <td className="p-2 text-red-400">${c.low}</td><td className="p-2">${c.close}</td>
                  <td className="p-2">{c.volume?.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
