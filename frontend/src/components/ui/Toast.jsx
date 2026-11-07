import { createContext, useContext, useState, useRef, useEffect } from 'react'
const Context = createContext(() => {})
// eslint-disable-next-line react-refresh/only-export-components
export const useToast = () => useContext(Context)
export function ToastProvider({ children }) {
  const [messages, setMessages] = useState([])
  const timers = useRef(new Set())
  useEffect(() => {
    const active = timers.current
    return () => active.forEach(clearTimeout)
  }, [])
  function notify(message) {
    const id = crypto.randomUUID()
    setMessages((m) => [...m, { id, message }])
    const timer = setTimeout(() => {
      setMessages((m) => m.filter((v) => v.id !== id))
      timers.current.delete(timer)
    }, 6000)
    timers.current.add(timer)
  }
  return (
    <Context.Provider value={notify}>
      {children}
      <div className="toasts" aria-live="polite">
        {messages.map((m) => (
          <div role="status" className="toast" key={m.id}>
            {m.message}
            <button
              aria-label="Закрыть уведомление"
              onClick={() => setMessages((items) => items.filter((v) => v.id !== m.id))}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </Context.Provider>
  )
}
