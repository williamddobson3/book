import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor
client.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
client.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    if (error.response) {
      throw new Error(error.response.data?.detail || error.message)
    }
    throw error
  }
)

export const api = {
  // Health check
  healthCheck: () => client.get('/health'),
  
  // Status
  getStatus: () => client.get('/status'),
  
  // Availability
  scanAvailability: () => client.post('/scan'),
  getAvailability: (params = {}) => client.get('/availability', { params }),
  
  // Booking
  bookSlot: (data) => client.post('/book', data),
  
  // Reservations
  getReservations: (limit = 100) => client.get('/reservations', { params: { limit } }),
  
  // Logs
  getLogs: (params = {}) => client.get('/logs', { params }),
}

export default client

