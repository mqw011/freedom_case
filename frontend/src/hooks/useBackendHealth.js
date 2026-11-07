import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'

export function useBackendHealth() {
  const [state, setState] = useState({ status: 'loading', message: 'Проверка соединения…' })
  useEffect(() => {
    let mounted = true
    let controller
    async function check() {
      controller?.abort()
      controller = new AbortController()
      try {
        const data = await getHealth(controller.signal)
        if (mounted) setState({ status: data.status === 'ok' ? 'online' : 'offline', message: 'Backend и база данных доступны' })
      } catch (error) {
        if (mounted && error.name !== 'AbortError') {
          setState({ status: 'offline', message: 'Нет соединения с backend. Проверьте запуск сервиса и VITE_API_BASE_URL.' })
        }
      }
    }
    check()
    const interval = setInterval(check, 30000)
    return () => { mounted = false; clearInterval(interval); controller?.abort() }
  }, [])
  return state
}
