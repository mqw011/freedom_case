import { useBackendHealth } from '../hooks/useBackendHealth'

export default function BackendStatus() {
  const { status, message } = useBackendHealth()
  return <div className={`connection ${status}`} role="status" aria-live="polite">
    <span className="status-dot" aria-hidden="true" />{message}
  </div>
}
