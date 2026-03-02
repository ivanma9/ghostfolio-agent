import { useState, useCallback } from 'react'

const AUTH_KEY = 'ghostfolio-auth'

interface AuthState {
  jwt: string
  role: 'admin' | 'user' | 'guest'
  userId: string
}

export function useAuth() {
  const [auth, setAuth] = useState<AuthState | null>(() => {
    const stored = localStorage.getItem(AUTH_KEY)
    if (!stored) return null
    try {
      return JSON.parse(stored)
    } catch {
      return null
    }
  })

  const login = useCallback(async (ghostfolioToken: string) => {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ghostfolio_token: ghostfolioToken }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(err.detail || 'Login failed')
    }
    const data = await resp.json()
    const state: AuthState = { jwt: data.token, role: data.role, userId: data.user_id }
    localStorage.setItem(AUTH_KEY, JSON.stringify(state))
    setAuth(state)
    return state
  }, [])

  const loginAsGuest = useCallback(async () => {
    const resp = await fetch('/api/auth/guest', { method: 'POST' })
    if (!resp.ok) throw new Error('Guest login failed')
    const data = await resp.json()
    const state: AuthState = { jwt: data.token, role: data.role, userId: data.user_id }
    localStorage.setItem(AUTH_KEY, JSON.stringify(state))
    setAuth(state)
    return state
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_KEY)
    localStorage.removeItem('ghostfolio-session-id')
    setAuth(null)
  }, [])

  return {
    auth,
    isAuthenticated: auth !== null,
    isGuest: auth?.role === 'guest',
    isAdmin: auth?.role === 'admin',
    login,
    loginAsGuest,
    logout,
  }
}
