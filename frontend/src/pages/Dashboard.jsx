import { useState, useEffect, useCallback } from 'react'
import { 
  Clock, CheckCircle, AlertCircle, RefreshCw, X, 
  Server, Activity, LogIn, PlayCircle, PauseCircle,
  AlertTriangle, Info, CheckCircle2, XCircle, Calendar,
  MapPin, BookOpen, Filter, ChevronDown, ChevronRight
} from 'lucide-react'
import { api } from '../api/client'
import { format } from 'date-fns'
import { useSSE } from '../hooks/useSSE'

export default function Dashboard() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [newReservationNotification, setNewReservationNotification] = useState(null)
  
  // Availability state
  const [slots, setSlots] = useState([])
  const [loadingSlots, setLoadingSlots] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [filter, setFilter] = useState({
    park_name: '',
    date_from: '',
    date_to: '',
  })
  const [selectedSlot, setSelectedSlot] = useState(null)
  const [booking, setBooking] = useState({ user_count: 2, event_name: '' })
  
  // Reservations state
  const [reservations, setReservations] = useState([])
  const [loadingReservations, setLoadingReservations] = useState(false)
  
  // Expansion state for parks and courts
  const [expandedParks, setExpandedParks] = useState(new Set())
  const [expandedCourts, setExpandedCourts] = useState(new Set())

  // Load availability slots (defined before handleSSEMessage to avoid initialization error)
  const loadAvailability = useCallback(async () => {
    try {
      setLoadingSlots(true)
      const params = {}
      if (filter.park_name) params.park_name = filter.park_name
      if (filter.date_from) params.date_from = filter.date_from
      if (filter.date_to) params.date_to = filter.date_to

      const response = await api.getAvailability(params)
      setSlots(response.slots || [])
    } catch (error) {
      console.error('Error loading availability:', error)
    } finally {
      setLoadingSlots(false)
    }
  }, [filter])

  // Handle SSE events for real-time updates
  const handleSSEMessage = useCallback((event) => {
    console.log('SSE message received:', event.type, event) // Debug logging
    
    if (event.type === 'reservation' && event.data) {
      const newReservation = event.data
      console.log('New reservation via SSE:', newReservation)
      setNewReservationNotification(newReservation)
      // Add to reservations list
      setReservations((prev) => {
        const exists = prev.some(r => r.id === newReservation.id)
        if (exists) {
          return prev
        }
        return [newReservation, ...prev]
      })
      setTimeout(() => {
        setNewReservationNotification(null)
      }, 5000)
    } else if (event.type === 'availability_update') {
      // New availability slots found - refresh the list
      console.log('Availability update received - refreshing slots')
      loadAvailability()
    } else if (event.type === 'connected' && event.status) {
      // Handle initial connection with current status
      console.log('SSE connected, updating status from initial connection:', event.status)
      setStatus(event.status)
      setLoading(false) // Stop loading since we have status now
    } else if (event.type === 'status_update' && event.data) {
      // Update status from SSE
      console.log('Status update received via SSE:', event.data)
      setStatus(event.data)
    } else if (event.type === 'keepalive' && event.status) {
      // Update status from keepalive
      console.log('Keepalive received, updating status:', event.status)
      setStatus(event.status)
    } else {
      console.warn('Unknown SSE event type:', event.type, event)
    }
  }, [loadAvailability])

  const handleSSEError = useCallback((error) => {
    console.error('SSE error:', error)
    // Log connection state if available
    if (error.target) {
      console.error('SSE connection state:', error.target.readyState)
      // EventSource readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
    }
  }, [])

  // Connect to SSE endpoint
  useSSE('/api/events', handleSSEMessage, handleSSEError)

  const loadStatus = useCallback(async () => {
    try {
      console.log('Loading status from API...')
      const response = await api.getStatus()
      console.log('Status API response:', response)
      if (response && response.status) {
        console.log('Setting status from API:', response.status)
        setStatus(response.status)
      } else if (response && response.error) {
        // If there's an error in the response, still set status to show the error
        console.error('Status response contains error:', response.error)
        if (response.status) {
          setStatus(response.status)
        }
      }
    } catch (error) {
      console.error('Error loading status:', error)
      // Set a minimal status to show connection error
      setStatus({
        system: {
          backend_status: 'Error',
          automation_status: 'Error',
          last_activity_time: null
        },
        login: {
          login_status: 'Unknown',
          session_status: 'Unknown',
          last_login_time: null,
          session_valid_until: null
        },
        current_task: {
          task: null,
          started_at: null,
          details: {}
        },
        activity_log: [],
        results: {
          last_check_time: null,
          last_availability_result: null,
          last_reservation_result: null
        },
        errors: {
          recent_errors: [{
            message: `Failed to connect to backend: ${error.message}`,
            timestamp: new Date().toISOString()
          }],
          recent_warnings: []
        }
      })
    } finally {
      setLoading(false)
    }
  }, [])

  // Load reservations
  const loadReservations = useCallback(async () => {
    try {
      setLoadingReservations(true)
      const response = await api.getReservations(100)
      setReservations(response.reservations || [])
    } catch (error) {
      console.error('Error loading reservations:', error)
    } finally {
      setLoadingReservations(false)
    }
  }, [])

  // Handle scan availability
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

  // Handle booking
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
      await loadReservations()
    } catch (error) {
      console.error('Booking error:', error)
      alert('予約に失敗しました: ' + error.message)
    }
  }

  const getParkOptions = () => {
    const parks = new Set(slots.map((s) => s.bcd_name))
    return Array.from(parks).sort()
  }

  const getReservationStatusIcon = (status) => {
    switch (status) {
      case 'confirmed':
        return <CheckCircle className="h-5 w-5 text-green-500" />
      case 'cancelled':
        return <XCircle className="h-5 w-5 text-red-500" />
      default:
        return <Clock className="h-5 w-5 text-yellow-500" />
    }
  }

  const getReservationStatusColor = (status) => {
    switch (status) {
      case 'confirmed':
        return 'bg-green-100 text-green-800'
      case 'cancelled':
        return 'bg-red-100 text-red-800'
      default:
        return 'bg-yellow-100 text-yellow-800'
    }
  }

  const getReservationStatusText = (status) => {
    switch (status) {
      case 'confirmed':
        return '確定'
      case 'cancelled':
        return 'キャンセル'
      default:
        return '保留'
    }
  }

  useEffect(() => {
    // Load initial status
    loadStatus()
    // Load availability and reservations
    loadAvailability()
    loadReservations()
    // Also refresh status every 10 seconds as a fallback (SSE should handle real-time updates)
    const interval = setInterval(() => {
      loadStatus()
      loadAvailability()
      loadReservations()
    }, 10000)
    return () => clearInterval(interval)
  }, [loadStatus, loadAvailability, loadReservations])

  const formatDate = (ymd) => {
    if (!ymd) return ''
    const dateStr = ymd.toString()
    const year = dateStr.substring(0, 4)
    const month = dateStr.substring(4, 6)
    const day = dateStr.substring(6, 8)
    const weekdays = ['日', '月', '火', '水', '木', '金', '土']
    const date = new Date(year, month - 1, day)
    const weekday = weekdays[date.getDay()]
    return `${year}年${month}月${day}日(${weekday})`
  }

  const formatTimestamp = (isoString) => {
    if (!isoString) return 'N/A'
    try {
      // Parse UTC ISO string
      const utcDate = new Date(isoString)
      // Check if date is valid
      if (isNaN(utcDate.getTime())) {
        return isoString
      }
      // Convert UTC to GMT+9 (Japan Standard Time) by adding 9 hours
      // GMT+9 = UTC + 9 hours = UTC + 9 * 60 * 60 * 1000 milliseconds
      const jstDate = new Date(utcDate.getTime() + (9 * 60 * 60 * 1000))
      // Format in GMT+9 timezone
      return format(jstDate, 'yyyy-MM-dd HH:mm:ss')
    } catch {
      return isoString
    }
  }


  const getStatusColor = (statusValue) => {
    if (statusValue === 'Running' || statusValue === 'Logged in' || statusValue === 'Active' || statusValue === 'Idle') {
      return 'text-green-600 bg-green-100'
    }
    if (statusValue === 'Processing') {
      return 'text-blue-600 bg-blue-100'
    }
    if (statusValue === 'Stopped' || statusValue === 'Not logged in' || statusValue === 'Expired' || statusValue === 'Error') {
      return 'text-red-600 bg-red-100'
    }
    return 'text-gray-600 bg-gray-100'
  }

  const getLogIcon = (level) => {
    switch (level) {
      case 'error':
        return <XCircle className="h-4 w-4 text-red-500" />
      case 'warning':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" />
      case 'info':
      default:
        return <Info className="h-4 w-4 text-blue-500" />
    }
  }

  if (loading && !status) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">読み込み中...</div>
      </div>
    )
  }

  if (!status) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-red-500">ステータスを取得できませんでした</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* New Reservation Notification */}
      {newReservationNotification && (
        <div className="bg-green-50 border-l-4 border-green-400 p-4 rounded-lg shadow-md animate-slide-in">
          <div className="flex items-center">
            <CheckCircle className="h-5 w-5 text-green-400 mr-3" />
            <div className="flex-1">
              <p className="text-sm font-medium text-green-800">
                新しい予約が作成されました！
              </p>
              <p className="text-sm text-green-700 mt-1">
                {newReservationNotification.bcd_name} - {newReservationNotification.icd_name} 
                {' '}({formatDate(newReservationNotification.use_ymd)} {newReservationNotification.start_time_display} ~ {newReservationNotification.end_time_display})
              </p>
              <p className="text-xs text-green-600 mt-1">
                予約番号: {newReservationNotification.reservation_number}
              </p>
            </div>
            <button
              onClick={() => setNewReservationNotification(null)}
              className="text-green-400 hover:text-green-600 transition-colors"
              aria-label="閉じる"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
      )}

      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">システムステータス</h2>
        <button
          onClick={loadStatus}
          className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
        >
          <RefreshCw className="h-4 w-4 mr-2" />
          更新
        </button>
      </div>

      {/* 1️⃣ System Status */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex items-center">
            <Server className="h-5 w-5 text-gray-600 mr-2" />
            <h3 className="text-lg font-semibold text-gray-900">システムステータス</h3>
          </div>
        </div>
        <div className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <p className="text-sm font-medium text-gray-600 mb-2">バックエンドステータス</p>
              <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(status.system?.backend_status)}`}>
                {status.system?.backend_status || 'Unknown'}
              </span>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-600 mb-2">自動化ステータス</p>
              <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(status.system?.automation_status)}`}>
                {status.system?.automation_status === 'Processing' && <Activity className="h-4 w-4 mr-1 animate-pulse" />}
                {status.system?.automation_status || 'Unknown'}
              </span>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-600 mb-2">最終活動時間</p>
              <p className="text-sm text-gray-900">
                {status.system?.last_activity_time ? formatTimestamp(status.system.last_activity_time) : 'N/A'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 2️⃣ Login / Session Status */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex items-center">
            <LogIn className="h-5 w-5 text-gray-600 mr-2" />
            <h3 className="text-lg font-semibold text-gray-900">ログイン / セッションステータス</h3>
          </div>
        </div>
        <div className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <p className="text-sm font-medium text-gray-600 mb-2">ログインステータス</p>
              <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(status.login?.login_status)}`}>
                {status.login?.login_status === 'Logged in' ? <CheckCircle2 className="h-4 w-4 mr-1" /> : <XCircle className="h-4 w-4 mr-1" />}
                {status.login?.login_status || 'Unknown'}
              </span>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-600 mb-2">セッション有効性</p>
              <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(status.login?.session_status)}`}>
                {status.login?.session_status || 'Unknown'}
              </span>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-600 mb-2">最終ログイン時間</p>
              <p className="text-sm text-gray-900">
                {status.login?.last_login_time ? formatTimestamp(status.login.last_login_time) : 'N/A'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 3️⃣ Current Task Status */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex items-center">
            <Activity className="h-5 w-5 text-gray-600 mr-2" />
            <h3 className="text-lg font-semibold text-gray-900">現在のタスクステータス</h3>
          </div>
        </div>
        <div className="p-6">
          {status.current_task?.task ? (
            <div>
              <div className="flex items-center mb-2">
                <PlayCircle className="h-5 w-5 text-blue-500 mr-2 animate-pulse" />
                <p className="text-lg font-medium text-gray-900">{status.current_task.task}</p>
              </div>
              {status.current_task.started_at && (
                <p className="text-sm text-gray-600">
                  開始: {formatTimestamp(status.current_task.started_at)}
                </p>
              )}
              {status.current_task.details && Object.keys(status.current_task.details).length > 0 && (
                <div className="mt-3 p-3 bg-gray-50 rounded-lg">
                  <p className="text-xs font-medium text-gray-600 mb-1">詳細:</p>
                  <pre className="text-xs text-gray-700 whitespace-pre-wrap">
                    {JSON.stringify(status.current_task.details, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center text-gray-500">
              <PauseCircle className="h-5 w-5 mr-2" />
              <p>現在実行中のタスクはありません</p>
            </div>
          )}
        </div>
      </div>

      {/* 4️⃣ Activity Log (Most Important) */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <Clock className="h-5 w-5 text-gray-600 mr-2" />
              <h3 className="text-lg font-semibold text-gray-900">アクティビティログ</h3>
            </div>
            <span className="text-sm text-gray-500">{status.activity_log?.length || 0} 件</span>
          </div>
        </div>
        <div className="p-6">
          {status.activity_log && status.activity_log.length > 0 ? (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {status.activity_log.map((log, index) => (
                <div
                  key={index}
                  className="flex items-start justify-between p-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-start flex-1">
                    <div className="mt-0.5 mr-2">
                      {getLogIcon(log.level)}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                          {log.category}
                        </span>
                        <span className="text-xs text-gray-400">
                          {formatTimestamp(log.timestamp)}
                        </span>
                      </div>
                      <p className="text-sm text-gray-900">{log.message}</p>
                      {log.data && Object.keys(log.data).length > 0 && (
                        <details className="mt-2">
                          <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700">
                            詳細を表示
                          </summary>
                          <pre className="mt-1 text-xs text-gray-600 bg-gray-50 p-2 rounded overflow-x-auto">
                            {JSON.stringify(log.data, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500">アクティビティログはありません</p>
          )}
        </div>
      </div>

      {/* 5️⃣ Result Summary */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex items-center">
            <CheckCircle className="h-5 w-5 text-gray-600 mr-2" />
            <h3 className="text-lg font-semibold text-gray-900">結果サマリー</h3>
          </div>
        </div>
        <div className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Availability Result */}
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-3">空き状況チェック</h4>
              {status.results?.last_availability_result ? (
                <div className="space-y-2">
                  <div className="flex items-center">
                    {status.results.last_availability_result.found ? (
                      <CheckCircle2 className="h-5 w-5 text-green-500 mr-2" />
                    ) : (
                      <XCircle className="h-5 w-5 text-gray-400 mr-2" />
                    )}
                    <span className={`font-medium ${status.results.last_availability_result.found ? 'text-green-600' : 'text-gray-600'}`}>
                      {status.results.last_availability_result.found ? '見つかりました' : '見つかりませんでした'}
                    </span>
                  </div>
                  {status.results.last_availability_result.slots_count > 0 && (
                    <p className="text-sm text-gray-600">
                      {status.results.last_availability_result.slots_count} スロット
                    </p>
                  )}
                  <p className="text-xs text-gray-500">
                    最終チェック: {formatTimestamp(status.results.last_availability_result.timestamp)}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-gray-500">まだチェックされていません</p>
              )}
            </div>

            {/* Reservation Result */}
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-3">予約結果</h4>
              {status.results?.last_reservation_result ? (
                <div className="space-y-2">
                  <div className="flex items-center">
                    {status.results.last_reservation_result.success ? (
                      <CheckCircle2 className="h-5 w-5 text-green-500 mr-2" />
                    ) : (
                      <XCircle className="h-5 w-5 text-red-500 mr-2" />
                    )}
                    <span className={`font-medium ${status.results.last_reservation_result.success ? 'text-green-600' : 'text-red-600'}`}>
                      {status.results.last_reservation_result.success ? '成功' : '失敗'}
                    </span>
                  </div>
                  {status.results.last_reservation_result.reservation_number && (
                    <p className="text-sm text-gray-600">
                      予約番号: {status.results.last_reservation_result.reservation_number}
                    </p>
                  )}
                  {status.results.last_reservation_result.error && (
                    <p className="text-sm text-red-600">
                      {status.results.last_reservation_result.error}
                    </p>
                  )}
                  <p className="text-xs text-gray-500">
                    {formatTimestamp(status.results.last_reservation_result.timestamp)}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-gray-500">まだ予約試行はありません</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 6️⃣ Error / Warning Display */}
      {(status.errors?.recent_errors?.length > 0 || status.errors?.recent_warnings?.length > 0) && (
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200">
            <div className="flex items-center">
              <AlertCircle className="h-5 w-5 text-red-600 mr-2" />
              <h3 className="text-lg font-semibold text-gray-900">エラー / 警告</h3>
            </div>
          </div>
          <div className="p-6">
            {/* Errors */}
            {status.errors?.recent_errors?.length > 0 && (
              <div className="mb-4">
                <h4 className="text-sm font-semibold text-red-700 mb-2">エラー</h4>
                <div className="space-y-2">
                  {status.errors.recent_errors.slice(0, 5).map((error, index) => (
                    <div key={index} className="p-3 bg-red-50 border-l-4 border-red-400 rounded">
                      <p className="text-sm text-red-800">{error.message}</p>
                      <p className="text-xs text-red-600 mt-1">
                        {formatTimestamp(error.timestamp)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Warnings */}
            {status.errors?.recent_warnings?.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-yellow-700 mb-2">警告</h4>
                <div className="space-y-2">
                  {status.errors.recent_warnings.slice(0, 5).map((warning, index) => (
                    <div key={index} className="p-3 bg-yellow-50 border-l-4 border-yellow-400 rounded">
                      <p className="text-sm text-yellow-800">{warning.message}</p>
                      <p className="text-xs text-yellow-600 mt-1">
                        {formatTimestamp(warning.timestamp)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 7️⃣ Available Slots */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex justify-between items-center">
            <div className="flex items-center">
              <Calendar className="h-5 w-5 text-gray-600 mr-2" />
              <h3 className="text-lg font-semibold text-gray-900">空き状況</h3>
            </div>
            <button
              onClick={handleScan}
              disabled={scanning}
              className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${scanning ? 'animate-spin' : ''}`} />
              スキャン
            </button>
          </div>
        </div>
        <div className="p-6">
          {/* Filters */}
          <div className="mb-6">
            <div className="flex items-center mb-4">
              <Filter className="h-4 w-4 text-gray-600 mr-2" />
              <h4 className="text-sm font-semibold text-gray-700">フィルター</h4>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">公園</label>
                <select
                  value={filter.park_name}
                  onChange={(e) => setFilter({ ...filter, park_name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                >
                  <option value="">すべて</option>
                  {getParkOptions().map((park) => (
                    <option key={park} value={park}>{park}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">開始日</label>
                <input
                  type="date"
                  value={filter.date_from}
                  onChange={(e) => setFilter({ ...filter, date_from: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">終了日</label>
                <input
                  type="date"
                  value={filter.date_to}
                  onChange={(e) => setFilter({ ...filter, date_to: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                />
              </div>
            </div>
          </div>

          {/* Slots List - Grouped by Park and Court */}
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-4">
              利用可能なスロット ({slots.length})
            </h4>
            {loadingSlots ? (
              <div className="text-center py-8">
                <RefreshCw className="h-6 w-6 text-gray-400 animate-spin mx-auto mb-2" />
                <p className="text-sm text-gray-500">読み込み中...</p>
              </div>
            ) : slots.length > 0 ? (
              (() => {
                // Group slots by park (bcd_name), then by court (icd_name)
                const groupedSlots = slots.reduce((acc, slot) => {
                  const parkName = slot.bcd_name || '不明な公園'
                  const courtName = slot.icd_name || '不明なコート'
                  
                  if (!acc[parkName]) {
                    acc[parkName] = {}
                  }
                  if (!acc[parkName][courtName]) {
                    acc[parkName][courtName] = []
                  }
                  acc[parkName][courtName].push(slot)
                  return acc
                }, {})
                
                // Sort parks and courts
                const sortedParks = Object.keys(groupedSlots).sort()
                
                // Toggle park expansion
                const togglePark = (parkName) => {
                  setExpandedParks(prev => {
                    const newSet = new Set(prev)
                    if (newSet.has(parkName)) {
                      newSet.delete(parkName)
                    } else {
                      newSet.add(parkName)
                    }
                    return newSet
                  })
                }
                
                // Toggle court expansion
                const toggleCourt = (parkName, courtName) => {
                  const courtKey = `${parkName}|${courtName}`
                  setExpandedCourts(prev => {
                    const newSet = new Set(prev)
                    if (newSet.has(courtKey)) {
                      newSet.delete(courtKey)
                    } else {
                      newSet.add(courtKey)
                    }
                    return newSet
                  })
                }
                
                return (
                  <div className="space-y-6">
                    {sortedParks.map((parkName) => {
                      const courts = groupedSlots[parkName]
                      const sortedCourts = Object.keys(courts).sort()
                      const totalSlotsInPark = Object.values(courts).reduce((sum, courtSlots) => sum + courtSlots.length, 0)
                      const isParkExpanded = expandedParks.has(parkName)
                      
                      return (
                        <div key={parkName} className="border border-gray-200 rounded-lg overflow-hidden">
                          {/* Park Header - Clickable */}
                          <div 
                            className="bg-gray-50 px-4 py-3 border-b border-gray-200 cursor-pointer hover:bg-gray-100 transition-colors"
                            onClick={() => togglePark(parkName)}
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center">
                                {isParkExpanded ? (
                                  <ChevronDown className="h-5 w-5 text-gray-600 mr-2" />
                                ) : (
                                  <ChevronRight className="h-5 w-5 text-gray-600 mr-2" />
                                )}
                                <MapPin className="h-5 w-5 text-gray-600 mr-2" />
                                <h5 className="text-base font-semibold text-gray-900">{parkName}</h5>
                                <span className="ml-3 text-xs text-gray-500">
                                  ({totalSlotsInPark} スロット)
                                </span>
                              </div>
                            </div>
                          </div>
                          
                          {/* Courts within Park - Conditionally Rendered */}
                          {isParkExpanded && (
                            <div className="p-4 space-y-4">
                              {sortedCourts.map((courtName) => {
                                const courtSlots = courts[courtName]
                                const courtKey = `${parkName}|${courtName}`
                                const isCourtExpanded = expandedCourts.has(courtKey)
                                
                                return (
                                  <div key={courtName} className="border border-gray-100 rounded-lg overflow-hidden">
                                    {/* Court Header - Clickable */}
                                    <div 
                                      className="bg-gray-100 px-4 py-2 border-b border-gray-200 cursor-pointer hover:bg-gray-200 transition-colors"
                                      onClick={() => toggleCourt(parkName, courtName)}
                                    >
                                      <div className="flex items-center justify-between">
                                        <div className="flex items-center">
                                          {isCourtExpanded ? (
                                            <ChevronDown className="h-4 w-4 text-gray-600 mr-2" />
                                          ) : (
                                            <ChevronRight className="h-4 w-4 text-gray-600 mr-2" />
                                          )}
                                          <BookOpen className="h-4 w-4 text-gray-600 mr-2" />
                                          <h6 className="text-sm font-medium text-gray-800">{courtName}</h6>
                                          <span className="ml-2 text-xs text-gray-500">
                                            ({courtSlots.length} スロット)
                                          </span>
                                        </div>
                                      </div>
                                    </div>
                                    
                                    {/* Slots in Court - Conditionally Rendered */}
                                    {isCourtExpanded && (
                                      <div className="p-4">
                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                          {courtSlots.map((slot) => (
                                            <div
                                              key={slot.id}
                                              className="border border-gray-200 rounded-lg p-3 hover:shadow-md transition-shadow cursor-pointer bg-white"
                                              onClick={() => setSelectedSlot(slot)}
                                            >
                                              <div className="flex items-start justify-between mb-2">
                                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                                  利用可能
                                                </span>
                                              </div>
                                              <div className="space-y-1.5">
                                                <div className="flex items-center text-xs text-gray-600">
                                                  <Calendar className="h-3 w-3 mr-1" />
                                                  {formatDate(slot.use_ymd)}
                                                </div>
                                                <div className="flex items-center text-xs text-gray-600">
                                                  <Clock className="h-3 w-3 mr-1" />
                                                  {slot.start_time_display} ~ {slot.end_time_display}
                                                </div>
                                              </div>
                                              <button
                                                onClick={(e) => {
                                                  e.stopPropagation()
                                                  setSelectedSlot(slot)
                                                }}
                                                className="mt-2 w-full px-2 py-1.5 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-medium"
                                              >
                                                予約する
                                              </button>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )
              })()
            ) : (
              <div className="text-center py-8">
                <Calendar className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                <p className="text-sm text-gray-500">利用可能なスロットがありません</p>
              </div>
            )}
          </div>
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
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
