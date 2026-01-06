import { useState, useEffect, useCallback } from 'react'
import { Calendar, Clock, MapPin, BookOpen, RefreshCw, Filter } from 'lucide-react'
import { api } from '../api/client'

export default function Availability() {
  const [slots, setSlots] = useState([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [filter, setFilter] = useState({
    park_name: '',
    date_from: '',
    date_to: '',
  })
  const [selectedSlot, setSelectedSlot] = useState(null)
  const [booking, setBooking] = useState({ user_count: 2, event_name: '' })

  const loadAvailability = useCallback(async () => {
    try {
      setLoading(true)
      const params = {}
      if (filter.park_name) params.park_name = filter.park_name
      if (filter.date_from) params.date_from = filter.date_from
      if (filter.date_to) params.date_to = filter.date_to

      const response = await api.getAvailability(params)
      setSlots(response.slots || [])
    } catch (error) {
      console.error('Error loading availability:', error)
      alert('空き状況の取得に失敗しました: ' + error.message)
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    loadAvailability()
  }, [loadAvailability])

  const handleScan = async () => {
    try {
      setScanning(true)
      await api.scanAvailability()
      await loadAvailability()
    } catch (error) {
      console.error('Scan error:', error)
      alert('スキャンに失敗しました: ' + error.message)
    } finally {
      setScanning(false)
    }
  }

  const handleBook = async () => {
    if (!selectedSlot) return

    try {
      const response = await api.bookSlot({
        slot_id: selectedSlot.id,
        user_count: booking.user_count,
        event_name: booking.event_name || null,
      })

      alert(`予約が完了しました！\n予約番号: ${response.reservation_number}`)
      setSelectedSlot(null)
      setBooking({ user_count: 2, event_name: '' })
      await loadAvailability()
    } catch (error) {
      console.error('Booking error:', error)
      alert('予約に失敗しました: ' + error.message)
    }
  }

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

  const getParkOptions = () => {
    const parks = new Set(slots.map((s) => s.bcd_name))
    return Array.from(parks).sort()
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">空き状況</h2>
        <button
          onClick={handleScan}
          disabled={scanning}
          className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${scanning ? 'animate-spin' : ''}`} />
          スキャン
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center mb-4">
          <Filter className="h-5 w-5 text-gray-600 mr-2" />
          <h3 className="text-lg font-semibold text-gray-900">フィルター</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              公園
            </label>
            <select
              value={filter.park_name}
              onChange={(e) => setFilter({ ...filter, park_name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">すべて</option>
              {getParkOptions().map((park) => (
                <option key={park} value={park}>
                  {park}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              開始日
            </label>
            <input
              type="date"
              value={filter.date_from}
              onChange={(e) => setFilter({ ...filter, date_from: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              終了日
            </label>
            <input
              type="date"
              value={filter.date_to}
              onChange={(e) => setFilter({ ...filter, date_to: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>
        </div>
      </div>

      {/* Slots List */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">
            利用可能なスロット ({slots.length})
          </h3>
        </div>
        <div className="p-6">
          {loading ? (
            <div className="text-center py-12">
              <RefreshCw className="h-8 w-8 text-gray-400 animate-spin mx-auto mb-4" />
              <p className="text-gray-500">読み込み中...</p>
            </div>
          ) : slots.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {slots.map((slot) => (
                <div
                  key={slot.id}
                  className="border border-gray-200 rounded-lg p-4 hover:shadow-lg transition-shadow cursor-pointer"
                  onClick={() => setSelectedSlot(slot)}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <div className="flex items-center mb-2">
                        <MapPin className="h-4 w-4 text-gray-500 mr-1" />
                        <p className="font-semibold text-gray-900">{slot.bcd_name}</p>
                      </div>
                      <p className="text-sm text-gray-600 mb-1">{slot.icd_name}</p>
                    </div>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      利用可能
                    </span>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center text-sm text-gray-600">
                      <Calendar className="h-4 w-4 mr-2" />
                      {formatDate(slot.use_ymd)}
                    </div>
                    <div className="flex items-center text-sm text-gray-600">
                      <Clock className="h-4 w-4 mr-2" />
                      {slot.start_time_display} ~ {slot.end_time_display}
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setSelectedSlot(slot)
                    }}
                    className="mt-3 w-full px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
                  >
                    予約する
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-500">利用可能なスロットがありません</p>
            </div>
          )}
        </div>
      </div>

      {/* Booking Modal */}
      {selectedSlot && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-md w-full p-6">
            <h3 className="text-xl font-bold text-gray-900 mb-4">予約確認</h3>
            <div className="space-y-4 mb-6">
              <div>
                <p className="text-sm text-gray-600">施設</p>
                <p className="font-medium text-gray-900">
                  {selectedSlot.bcd_name} - {selectedSlot.icd_name}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-600">日時</p>
                <p className="font-medium text-gray-900">
                  {formatDate(selectedSlot.use_ymd)} {selectedSlot.start_time_display} ~{' '}
                  {selectedSlot.end_time_display}
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  利用人数 *
                </label>
                <input
                  type="number"
                  min="1"
                  value={booking.user_count}
                  onChange={(e) =>
                    setBooking({ ...booking, user_count: parseInt(e.target.value) || 1 })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  催し物名（任意）
                </label>
                <input
                  type="text"
                  value={booking.event_name}
                  onChange={(e) => setBooking({ ...booking, event_name: e.target.value })}
                  placeholder="例: サークル練習会"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
            </div>
            <div className="flex space-x-3">
              <button
                onClick={() => setSelectedSlot(null)}
                className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
              >
                キャンセル
              </button>
              <button
                onClick={handleBook}
                className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                <BookOpen className="h-4 w-4 inline mr-2" />
                予約確定
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

