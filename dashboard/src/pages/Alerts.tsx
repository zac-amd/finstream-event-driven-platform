import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, AlertCircle, Bell } from 'lucide-react'

export default function Alerts() {
  const { data, isLoading } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => fetch('/api/v1/alerts?limit=50').then(r => r.json()),
  })

  const severityIcon = (s: string) => {
    if (s === 'CRITICAL') return <AlertTriangle className="w-5 h-5 text-red-500" />
    if (s === 'HIGH') return <AlertCircle className="w-5 h-5 text-orange-500" />
    return <Bell className="w-5 h-5 text-yellow-500" />
  }

  if (isLoading) return <div className="text-center py-8">Loading...</div>

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Recent Alerts</h1>
      <div className="space-y-3">
        {data?.alerts?.map((a: any) => (
          <div key={a.alert_id} className="bg-gray-800 rounded-lg p-4 flex items-start gap-4">
            {severityIcon(a.severity)}
            <div className="flex-1">
              <div className="flex justify-between">
                <span className="font-bold">{a.symbol}</span>
                <span className="text-gray-400 text-sm">{new Date(a.timestamp).toLocaleString()}</span>
              </div>
              <p className="text-sm mt-1">{a.message}</p>
              <span className={`text-xs px-2 py-1 rounded mt-2 inline-block ${
                a.alert_type === 'PRICE_SPIKE' ? 'bg-blue-900' : 
                a.alert_type === 'VOLUME_ANOMALY' ? 'bg-purple-900' : 'bg-gray-700'
              }`}>{a.alert_type}</span>
            </div>
          </div>
        ))}
        {(!data?.alerts || data.alerts.length === 0) && (
          <div className="text-center text-gray-400 py-8">No alerts yet</div>
        )}
      </div>
    </div>
  )
}
