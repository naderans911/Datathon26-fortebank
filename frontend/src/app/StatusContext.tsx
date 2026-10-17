import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { getStatus } from '../lib/api'
import type { SystemStatus } from '../lib/types'
const Context = createContext<{ status: SystemStatus | null; error: string; refresh: () => void }>({
  status: null,
  error: '',
  refresh: () => {},
})
export function StatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [error, setError] = useState('')
  const refresh = useCallback(() => {
    getStatus()
      .then((s) => {
        setStatus(s)
        setError('')
      })
      .catch((e) => {
        setStatus(null)
        setError(e.message)
      })
  }, [])
  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 15000)
    return () => clearInterval(timer)
  }, [refresh])
  return <Context.Provider value={{ status, error, refresh }}>{children}</Context.Provider>
}
export const useStatus = () => useContext(Context)
