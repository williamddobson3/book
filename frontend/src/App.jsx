import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Availability from './pages/Availability'
import Reservations from './pages/Reservations'

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/availability" element={<Availability />} />
          <Route path="/reservations" element={<Reservations />} />
        </Routes>
      </Layout>
    </Router>
  )
}

export default App

