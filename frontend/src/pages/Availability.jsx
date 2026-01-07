import { useState, useEffect, useCallback } from 'react'
import { Calendar, Clock, MapPin, BookOpen, RefreshCw, Filter, CheckCircle } from 'lucide-react'
import { api } from '../api/client'

export default function Availability() {
  const [slots, setSlots] = useState([])
  const [reservations, setReservations] = useState([])
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

      // Load both availability slots and reservations
      const [availabilityResponse, reservationsResponse] = await Promise.all([
        api.getAvailability(params),
        api.getReservations(100)
      ])
      
      setSlots(availabilityResponse.slots || [])
      // Flatten reservations from grouped_by_date if available
      const reservationsList = reservationsResponse.grouped_by_date 
        ? reservationsResponse.grouped_by_date.flatMap(group => group.reservations)
        : reservationsResponse.reservations || []
      setReservations(reservationsList)
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
      // Reload both availability and reservations
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

  // Group slots (both available and reserved) by date FIRST, then by park, then by court
  // Structure: Date → Park → Court → Slots (available + reserved)
  const groupSlotsByDate = () => {
    const grouped = {}
    
    // Step 1: Add available slots (mark as available)
    slots.forEach((slot) => {
      const dateKey = slot.use_ymd.toString()
      
      if (!grouped[dateKey]) {
        grouped[dateKey] = {
          date: slot.use_ymd,
          parks: {}
        }
      }
      
      // Step 2: Within each date, group by PARK (SECONDARY grouping)
      const parkKey = slot.bcd_name
      if (!grouped[dateKey].parks[parkKey]) {
        grouped[dateKey].parks[parkKey] = []
      }
      
      // Mark as available slot
      grouped[dateKey].parks[parkKey].push({
        ...slot,
        is_reserved: false,
        type: 'available'
      })
    })
    
    // Step 3: Add reservations (mark as reserved)
    reservations.forEach((reservation) => {
      const dateKey = reservation.use_ymd.toString()
      
      if (!grouped[dateKey]) {
        grouped[dateKey] = {
          date: reservation.use_ymd,
          parks: {}
        }
      }
      
      const parkKey = reservation.bcd_name
      if (!grouped[dateKey].parks[parkKey]) {
        grouped[dateKey].parks[parkKey] = []
      }
      
      // Mark as reserved slot
      grouped[dateKey].parks[parkKey].push({
        ...reservation,
        is_reserved: true,
        type: 'reserved'
      })
    })
    
    // Sort dates numerically (earliest date first)
    const sortedDates = Object.keys(grouped).sort((a, b) => {
      return parseInt(a) - parseInt(b)
    })
    
    // DEBUG: Log the structure
    console.log('Grouped by Date:', sortedDates.map(dateKey => ({
      date: grouped[dateKey].date,
      parks: Object.keys(grouped[dateKey].parks)
    })))
    
    // Return: Date → Park → Court structure
    return sortedDates.map(dateKey => {
      const dateGroup = grouped[dateKey]
      
      // For each date, organize parks (which contain courts)
      const parks = Object.keys(dateGroup.parks)
        .sort() // Sort parks alphabetically
        .map(parkName => {
          const parkSlots = dateGroup.parks[parkName]
          
          // Step 3: Group slots by COURT (facility) within each park (TERTIARY grouping)
          const courts = {}
          parkSlots.forEach(slot => {
            const courtKey = slot.icd_name
            if (!courts[courtKey]) {
              courts[courtKey] = []
            }
            courts[courtKey].push(slot)
          })
          
          // Sort courts alphabetically and slots by time
          const courtList = Object.keys(courts)
            .sort()
            .map(courtName => ({
              name: courtName,
              slots: courts[courtName].sort((a, b) => 
                a.start_time_display.localeCompare(b.start_time_display)
              )
            }))
          
          return {
            name: parkName,
            courts: courtList,
            totalSlots: parkSlots.length
          }
        })
      
      return {
        date: dateGroup.date,
        parks: parks
      }
    })
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
            利用可能なスロット ({slots.length}) / 予約済み ({reservations.length})
          </h3>
        </div>
        <div className="p-6">
          {loading ? (
            <div className="text-center py-12">
              <RefreshCw className="h-8 w-8 text-gray-400 animate-spin mx-auto mb-4" />
              <p className="text-gray-500">読み込み中...</p>
            </div>
          ) : (slots.length > 0 || reservations.length > 0) ? (
            <div className="space-y-6">
              {groupSlotsByDate().map((dateGroup) => (
                <div key={dateGroup.date} className="border-2 border-primary-300 rounded-lg overflow-hidden mb-6 shadow-lg">
                  {/* DATE HEADER - TOP LEVEL (most prominent) */}
                  <div className="bg-gradient-to-r from-primary-500 to-primary-600 px-6 py-5 border-b-2 border-primary-700">
                    <div className="flex items-center">
                      <Calendar className="h-6 w-6 text-white mr-3" />
                      <h3 className="text-2xl font-bold text-white">
                        {formatDate(dateGroup.date)}
                      </h3>
                      <span className="ml-auto text-base font-semibold text-white bg-primary-700 px-3 py-1 rounded-full">
                        {dateGroup.parks.reduce((sum, park) => sum + park.totalSlots, 0)} スロット
                      </span>
                    </div>
                  </div>

                  {/* Parks (within Date) */}
                  <div className="p-6 space-y-4">
                    {dateGroup.parks.map((park) => (
                      <div key={park.name} className="border border-gray-200 rounded-lg p-4">
                        {/* Park Header */}
                        <div className="flex items-center mb-4 pb-3 border-b border-gray-200">
                          <MapPin className="h-4 w-4 text-gray-500 mr-2" />
                          <h5 className="font-semibold text-gray-900">{park.name}</h5>
                          <span className="ml-auto text-sm text-gray-600">
                            ({park.totalSlots} スロット)
                          </span>
                        </div>

                        {/* Courts (within Park) */}
                        <div className="space-y-3">
                          {park.courts.map((court) => (
                            <div key={court.name} className="pl-4 border-l-2 border-gray-300">
                              <p className="text-sm font-medium text-gray-700 mb-2">
                                {court.name} ({court.slots.length} スロット)
                              </p>
                              
                              {/* Slots for this court - both available and reserved */}
                              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                {court.slots.map((slot) => (
                                  <div
                                    key={slot.id || `reserved-${slot.reservation_number}`}
                                    className={`rounded-lg p-3 transition-colors border-2 ${
                                      slot.is_reserved
                                        ? 'bg-blue-50 border-blue-300 hover:bg-blue-100'
                                        : 'bg-gray-50 border-gray-200 hover:bg-gray-100'
                                    }`}
                                  >
                                    <div className="flex items-start justify-between mb-2">
                                      {slot.is_reserved ? (
                                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                          <CheckCircle className="h-3 w-3 mr-1" />
                                          予約済み
                                        </span>
                                      ) : (
                                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                          利用可能
                                        </span>
                                      )}
                                    </div>
                                    <div className="flex items-center text-sm text-gray-600 mb-3">
                                      <Clock className="h-4 w-4 mr-1" />
                                      {slot.start_time_display} ~ {slot.end_time_display}
                                    </div>
                                    {slot.is_reserved ? (
                                      <div className="space-y-1 text-xs">
                                        {slot.reservation_number && (
                                          <div className="text-gray-600">
                                            予約番号: <span className="font-mono font-semibold">{slot.reservation_number}</span>
                                          </div>
                                        )}
                                        {slot.user_count && (
                                          <div className="text-gray-600">
                                            利用人数: {slot.user_count}人
                                          </div>
                                        )}
                                        {slot.event_name && (
                                          <div className="text-gray-600">
                                            {slot.event_name}
                                          </div>
                                        )}
                                      </div>
                                    ) : (
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          setSelectedSlot(slot)
                                        }}
                                        className="w-full px-3 py-1.5 bg-primary-600 text-white rounded-md hover:bg-primary-700 transition-colors text-sm font-medium"
                                      >
                                        予約する
                                      </button>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
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

