import { HashRouter, NavLink, Route, Routes } from 'react-router-dom'
import BackendStatus from './components/BackendStatus'
import Dashboard from './pages/Dashboard'
import StageThreePage from './pages/StageThreePage'

export default function App() {
  return <HashRouter>
    <header><div className="brand"><span className="brand-mark">F</span>Freedom Broker <span className="product">CQA</span></div><BackendStatus /></header>
    <div className="workspace">
      <nav aria-label="Основная навигация">
        <NavLink to="/" end>Обзор</NavLink>
        <NavLink to="/conversations">Диалоги</NavLink>
        <NavLink to="/checklists">Чек-листы</NavLink>
        <NavLink to="/appeals">Апелляции</NavLink>
      </nav>
      <main><Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/conversations" element={<StageThreePage page="conversations" />} />
        <Route path="/conversations/:id" element={<StageThreePage page="details" />} />
        <Route path="/checklists" element={<StageThreePage page="checklist" />} />
        <Route path="/appeals" element={<StageThreePage page="appeals" />} />
        <Route path="*" element={<section><h1>Страница не найдена</h1><NavLink to="/">Вернуться к обзору</NavLink></section>} />
      </Routes></main>
    </div>
    <footer>Freedom Broker · Conversation Quality Analytics · Stage 1</footer>
  </HashRouter>
}
