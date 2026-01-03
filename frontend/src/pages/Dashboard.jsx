import { useState, useEffect } from 'react'
import { Calendar, Clock, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react'
import { api } from '../api/client'
import { format } from 'date-fns'

export default function Dashboard() {
  const [stats, setStats] = useState({
    available: 0,
    reservations: 0,
    scanning: false,
  })
  const [recentReservations, setRecentReservations] = useState([])
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadDashboard()
  }, [])

  const loadDashboard = async () => {
    try {
      setLoading(true)
      const [availabilityRes, reservationsRes, logsRes] = await Promise.all([
        api.getAvailability(),
        api.getReservations(5),
        api.getLogs({ limit: 10 }),
      ])

      setStats({
        available: availabilityRes.count || 0,
        reservations: reservationsRes.count || 0,
        scanning: false,
      })
      setRecentReservations(reservationsRes.reservations || [])
      setLogs(logsRes.logs || [])
    } catch (error) {
      console.error('Error loading dashboard:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleScan = async () => {
    try {
      setStats((prev) => ({ ...prev, scanning: true }))
      await api.scanAvailability()
      await loadDashboard()
    } catch (error) {
      console.error('Scan error:', error)
      alert('スキャンに失敗しました: ' + error.message)
    } finally {
      setStats((prev) => ({ ...prev, scanning: false }))
    }
  }

  const formatDate = (ymd) => {
    const dateStr = ymd.toString()
    const year = dateStr.substring(0, 4)
    const month = dateStr.substring(4, 6)
    const day = dateStr.substring(6, 8)
    return `${year}年${month}月${day}日`
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">ダッシュボード</h2>
        <button
          onClick={handleScan}
          disabled={stats.scanning}
          className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${stats.scanning ? 'animate-spin' : ''}`} />
          空き状況をスキャン
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="p-3 bg-blue-100 rounded-lg">
              <Calendar className="h-6 w-6 text-blue-600" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600">利用可能なスロット</p>
              <p className="text-2xl font-bold text-gray-900">{stats.available}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="p-3 bg-green-100 rounded-lg">
              <CheckCircle className="h-6 w-6 text-green-600" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600">予約済み</p>
              <p className="text-2xl font-bold text-gray-900">{stats.reservations}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="p-3 bg-purple-100 rounded-lg">
              <Clock className="h-6 w-6 text-purple-600" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600">システムステータス</p>
              <p className="text-2xl font-bold text-gray-900">稼働中</p>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Reservations */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">最近の予約</h3>
        </div>
        <div className="p-6">
          {loading ? (
            <p className="text-gray-500">読み込み中...</p>
          ) : recentReservations.length > 0 ? (
            <div className="space-y-4">
              {recentReservations.map((reservation) => (
                <div
                  key={reservation.id}
                  className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <div>
                    <p className="font-medium text-gray-900">
                      {reservation.bcd_name} - {reservation.icd_name}
                    </p>
                    <p className="text-sm text-gray-600">
                      {formatDate(reservation.use_ymd)} {reservation.start_time_display} ~ {reservation.end_time_display}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium text-gray-900">
                      予約番号: {reservation.reservation_number}
                    </p>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      {reservation.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500">予約はありません</p>
          )}
        </div>
      </div>

      {/* Recent Logs */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">最近のログ</h3>
        </div>
        <div className="p-6">
          {logs.length > 0 ? (
            <div className="space-y-2">
              {logs.map((log) => (
                <div
                  key={log.id}
                  className="flex items-center justify-between p-3 border border-gray-200 rounded-lg"
                >
                  <div className="flex items-center">
                    {log.success ? (
                      <CheckCircle className="h-4 w-4 text-green-500 mr-2" />
                    ) : (
                      <AlertCircle className="h-4 w-4 text-red-500 mr-2" />
                    )}
                    <p className="text-sm text-gray-900">{log.message}</p>
                  </div>
                  <p className="text-xs text-gray-500">
                    {format(new Date(log.created_at), 'MM/dd HH:mm')}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500">ログはありません</p>
          )}
        </div>
      </div>
    </div>
  )
}

