import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

export default function Login() {
  const navigate = useNavigate()
  const login = useAuthStore((state) => state.login)
  const [isRegister, setIsRegister] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    username: '',
    full_name: '',
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      if (isRegister) {
        // Register
        const regRes = await fetch('/api/v1/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formData),
        })
        
        if (!regRes.ok) {
          const data = await regRes.json()
          throw new Error(data.detail || 'Registration failed')
        }
      }

      // Login
      const loginRes = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: formData.email,
          password: formData.password,
        }),
      })

      if (!loginRes.ok) {
        const data = await loginRes.json()
        throw new Error(data.detail || 'Login failed')
      }

      const tokens = await loginRes.json()

      // Get user profile
      const meRes = await fetch('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${tokens.access_token}` },
      })
      const user = await meRes.json()

      login(tokens.access_token, tokens.refresh_token, user)
      navigate('/portfolio')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center px-4">
      <div className="max-w-md w-full">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white">FinStream</h1>
          <p className="text-gray-400 mt-2">Paper Trading Platform</p>
        </div>

        <div className="bg-gray-800 rounded-lg p-8">
          <div className="flex mb-6">
            <button
              className={`flex-1 py-2 text-center rounded-l-lg ${
                !isRegister ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400'
              }`}
              onClick={() => setIsRegister(false)}
            >
              Login
            </button>
            <button
              className={`flex-1 py-2 text-center rounded-r-lg ${
                isRegister ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400'
              }`}
              onClick={() => setIsRegister(true)}
            >
              Register
            </button>
          </div>

          {error && (
            <div className="bg-red-900/50 border border-red-500 text-red-200 px-4 py-3 rounded mb-4">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-gray-400 text-sm mb-1">Email</label>
              <input
                type="email"
                required
                className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>

            {isRegister && (
              <>
                <div>
                  <label className="block text-gray-400 text-sm mb-1">Username</label>
                  <input
                    type="text"
                    required
                    minLength={3}
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500"
                    value={formData.username}
                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-gray-400 text-sm mb-1">Full Name (optional)</label>
                  <input
                    type="text"
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500"
                    value={formData.full_name}
                    onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                  />
                </div>
              </>
            )}

            <div>
              <label className="block text-gray-400 text-sm mb-1">Password</label>
              <input
                type="password"
                required
                minLength={8}
                className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white font-semibold rounded transition-colors"
            >
              {loading ? 'Please wait...' : isRegister ? 'Create Account' : 'Sign In'}
            </button>
          </form>

          <div className="mt-6 text-center text-gray-400 text-sm">
            <Link to="/" className="hover:text-white">
              ← Back to Dashboard
            </Link>
          </div>
        </div>

        <div className="mt-6 text-center text-gray-500 text-sm">
          Start with $10,000 virtual cash. No real money involved.
        </div>
      </div>
    </div>
  )
}
