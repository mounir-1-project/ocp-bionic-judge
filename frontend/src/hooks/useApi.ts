import { useState, useEffect, useCallback, useRef } from 'react'

export interface UseApiResult<T> {
  data:    T | null
  loading: boolean
  error:   string | null
  refresh: () => Promise<void>
  lastAt:  Date | null
}

/**
 * Typed data-fetching hook with stale-while-revalidate polling.
 *
 * - `loading` is true ONLY until the first response (initial render skeleton).
 * - Interval refreshes run silently — no UI flash every 30 s.
 * - Generic <T> propagates the exact return type from `fetcher`.
 */
export function useApi<T>(
  fetcher:  () => Promise<T>,
  deps:     unknown[] = [],
  interval  = 30_000,
): UseApiResult<T> {
  const [data,    setData]    = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)
  const [lastAt,  setLastAt]  = useState<Date | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  const run = useCallback(async () => {
    try {
      const result = await fetcher()
      if (!mountedRef.current) return
      setData(result)
      setError(null)
      setLastAt(new Date())
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : 'Erreur inconnue')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    setLoading(true)
    setData(null)
    setError(null)
    void run()
    const timer = setInterval(run, interval)
    return () => clearInterval(timer)
  }, [run, interval])

  return { data, loading, error, refresh: run, lastAt }
}
