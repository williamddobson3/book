import { useState, useEffect, useCallback } from 'react'
import { Clock, Calendar, MapPin, CheckCircle, XCircle } from 'lucide-react'
import { api } from '../api/client'
import { format } from 'date-fns'
import { useSSE } from '../hooks/useSSE'

export default function Reservations() {
  const [reservations, setReservations] = useState([])
  const [loading, setLoading] = useState(true)

  // Handle SSE events for real-time reservation updates
  const handleSSEMessage = useCallback((event) => {
    if (event.type === 'reservation' && event.data) {
      const newReservation = event.data
      console.log('New reservation received via SSE:', newReservation)
      
      // Add new reservation to the top of the list
      setReservations((prev) => {
        // Check if reservation already exists (avoid duplicates)
        const exists = prev.some(r => r.id === newReservation.id)
        if (exists) {
          return prev
        }
        // Add to the beginning of the list (most recent first)
        return [newReservation, ...prev]
      })
    }
  }, [])

  const handleSSEError = useCallback((error) => {
    console.error('SSE error:', error)
  }, [])

  // Connect to SSE endpoint
  useSSE('/api/events', handleSSEMessage, handleSSEError)

  const loadReservations = useCallback(async () => {
    try {
      setLoading(true)
      const response = await api.getReservations(100)
      setReservations(response.reservations || [])
    } catch (error) {
      console.error('Error loading reservations:', error)
      alert('予約一覧の取得に失敗しました: ' + error.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadReservations()
  }, [loadReservations])

  const formatDate = (ymd) => {
    const dateStr = ymd.toString()
    const year = dateStr.substring(0, 4)
    const month = dateStr.substring(4, 6)
    const day = dateStr.substring(6, 8)
    const weekdays = ['日', '月', '火', '水', '木', '金', '土']
    const date = new Date(year, month - 1, day)
    const weekday = weekdays[date.getDay()]
    return `${year}年${month}月${day}日(${weekday})`
  }

  const getStatusIcon = (status) => {
    switch (status) {
      case 'confirmed':
        return <CheckCircle className="h-5 w-5 text-green-500" />
      case 'cancelled':
        return <XCircle className="h-5 w-5 text-red-500" />
      default:
        return <Clock className="h-5 w-5 text-yellow-500" />
    }
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'confirmed':
        return 'bg-green-100 text-green-800'
      case 'cancelled':
        return 'bg-red-100 text-red-800'
      default:
        return 'bg-yellow-100 text-yellow-800'
    }
  }

  const getStatusText = (status) => {
    switch (status) {
      case 'confirmed':
        return '確定'
      case 'cancelled':
        return 'キャンセル'
      default:
        return '保留'
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">予約一覧</h2>
        <button
          onClick={loadReservations}
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm font-medium"
        >
          更新
        </button>
      </div>

      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">
            予約履歴 ({reservations.length})
          </h3>
        </div>
        <div className="p-6">
          {loading ? (
            <div className="text-center py-12">
              <Clock className="h-8 w-8 text-gray-400 animate-pulse mx-auto mb-4" />
              <p className="text-gray-500">読み込み中...</p>
            </div>
          ) : reservations.length > 0 ? (
            <div className="space-y-4">
              {reservations.map((reservation) => (
                <div
                  key={reservation.id}
                  className="border border-gray-200 rounded-lg p-6 hover:shadow-lg transition-shadow"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1">
                      <div className="flex items-center mb-2">
                        <MapPin className="h-5 w-5 text-gray-500 mr-2" />
                        <h4 className="text-lg font-semibold text-gray-900">
                          {reservation.bcd_name} - {reservation.icd_name}
                        </h4>
                      </div>
                      <div className="ml-7 space-y-2">
                        <div className="flex items-center text-gray-600">
                          <Calendar className="h-4 w-4 mr-2" />
                          {formatDate(reservation.use_ymd)}
                        </div>
                        <div className="flex items-center text-gray-600">
                          <Clock className="h-4 w-4 mr-2" />
                          {reservation.start_time_display} ~ {reservation.end_time_display}
                        </div>
                        <div className="text-sm text-gray-600">
                          利用人数: {reservation.user_count}人
                        </div>
                        {reservation.event_name && (
                          <div className="text-sm text-gray-600">
                            催し物名: {reservation.event_name}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="flex items-center justify-end mb-2">
                        {getStatusIcon(reservation.status)}
                        <span
                          className={`ml-2 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(
                            reservation.status
                          )}`}
                        >
                          {getStatusText(reservation.status)}
                        </span>
                      </div>
                      <div className="text-sm text-gray-600">
                        予約番号
                      </div>
                      <div className="text-sm font-mono font-semibold text-gray-900">
                        {reservation.reservation_number}
                      </div>
                      <div className="text-xs text-gray-500 mt-2">
                        {(() => {
                          try {
                            const utcDate = new Date(reservation.created_at)
                            if (isNaN(utcDate.getTime())) return 'N/A'
                            // Convert UTC to GMT+9 (Japan Standard Time) by adding 9 hours
                            const jstDate = new Date(utcDate.getTime() + (9 * 60 * 60 * 1000))
                            return format(jstDate, 'yyyy/MM/dd HH:mm')
                          } catch {
                            return 'N/A'
                          }
                        })()}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <Clock className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-500">予約履歴がありません</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

