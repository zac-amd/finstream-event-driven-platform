import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface User {
  id: string
  email: string
  username: string
  full_name: string | null
}

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  login: (accessToken: string, refreshToken: string, user: User) => void
  logout: () => void
  setUser: (user: User) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      login: (accessToken, refreshToken, user) =>
        set({ accessToken, refreshToken, user, isAuthenticated: true }),
      logout: () =>
        set({ accessToken: null, refreshToken: null, user: null, isAuthenticated: false }),
      setUser: (user) => set({ user }),
    }),
    {
      name: 'finstream-auth',
    }
  )
)

// API helper with auth
export const authFetch = async (url: string, options: RequestInit = {}) => {
  const { accessToken } = useAuthStore.getState()
  
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  }
  
  if (accessToken) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${accessToken}`
  }
  
  const response = await fetch(url, { ...options, headers })
  
  if (response.status === 401) {
    useAuthStore.getState().logout()
    window.location.href = '/login'
  }
  
  return response
}
