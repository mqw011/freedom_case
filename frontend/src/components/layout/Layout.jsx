import { useState, useEffect, useRef } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  MessagesSquare,
  ClipboardCheck,
  Scale,
  ListTodo,
  Database,
  Menu,
  X,
  ArrowUpRight,
} from 'lucide-react'
import BackendStatus from '../BackendStatus'
import { Button } from '../ui'
const nav = [
  ['/', 'Обзор', LayoutDashboard],
  ['/conversations', 'Диалоги', MessagesSquare],
  ['/checklists', 'Чек-листы', ClipboardCheck],
  ['/appeals', 'Апелляции', Scale],
  ['/ai-jobs', 'AI задания', ListTodo],
  ['/datasets', 'Импорт данных', Database],
]
export default function Layout() {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const sidebar = useRef()
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement
    sidebar.current.querySelector('a').focus()
    return () => previous?.focus()
  }, [open])
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [location.pathname])
  function menuKeys(e) {
    if (!open) return
    if (e.key === 'Escape') {
      setOpen(false)
      return
    }
    if (e.key === 'Tab') {
      const items = [...sidebar.current.querySelectorAll('a,button')]
      const first = items[0],
        last = items.at(-1)
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
  }

  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(e) => {
          e.preventDefault()
          const main = document.getElementById('main-content')
          main?.focus()
          main?.scrollIntoView({ block: 'start' })
        }}
      >
        Перейти к содержимому
      </a>
      <aside ref={sidebar} onKeyDown={menuKeys} className={`sidebar ${open ? 'open' : ''}`}>
        <NavLink to="/" className="brand" onClick={() => setOpen(false)}>
          <span className="brand-symbol">
            F<span>↗</span>
          </span>
          <span>
            freedom<span className="brand-sub">CONVERSATION QUALITY</span>
          </span>
        </NavLink>
        <Button variant="ghost" className="sidebar-close" onClick={() => setOpen(false)}>
          Закрыть меню
        </Button>
        <div className="sidebar-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav aria-label="Основная навигация">
          {nav.map(([path, label, Icon]) => (
            <NavLink key={path} end={path === '/'} to={path} onClick={() => setOpen(false)}>
              <Icon size={19} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace-avatar">QA</div>
          <div>
            <strong>Quality workspace</strong>
            <small>Freedom Broker · CQA</small>
          </div>
        </div>
      </aside>
      {open && (
        <button className="nav-backdrop" aria-label="Закрыть меню" onClick={() => setOpen(false)} />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="actions">
            <Button
              variant="ghost"
              className="menu-toggle"
              aria-label={open ? 'Закрыть меню' : 'Открыть меню'}
              aria-expanded={open}
              onClick={() => setOpen(!open)}
            >
              {open ? <X size={20} /> : <Menu size={20} />}
            </Button>
            <span className="breadcrumb">
              Рабочее пространство <span>/</span>{' '}
              {nav.find(([p]) =>
                p === '/' ? location.pathname === '/' : location.pathname.startsWith(p),
              )?.[1] || 'Детали'}
            </span>
          </div>
          <span className="local-label">
            <span className="dot" /> CQA · Workspace <ArrowUpRight size={14} />
          </span>
        </header>
        {import.meta.env.VITE_DEMO_MODE === 'true' && (
          <div className="demo-banner">
            ТЕСТОВОЕ ОКРУЖЕНИЕ · Только синтетические данные · Оценки manual/test
          </div>
        )}
        <main id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
        <footer>
          <span>Freedom Broker CQA</span>
          <BackendStatus />
        </footer>
      </div>
    </div>
  )
}
