import { HashRouter, Route, Routes, Link } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from './components/ui/Toast'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Conversations from './pages/Conversations'
import ConversationDetail from './pages/ConversationDetail'
import Checklists from './pages/Checklists'
import Appeals from './pages/Appeals'
import AppealDetail from './pages/AppealDetail'
import AIJobs from './pages/AIJobs'
import AIJobDetail from './pages/AIJobDetail'
import AIBatchDetail from './pages/AIBatchDetail'
import Datasets from './pages/Datasets'
const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10000,
      gcTime: 300000,
      refetchOnWindowFocus: true,
      retry: (count, error) => count < 1 && (!error.status || error.status >= 500),
    },
    mutations: { retry: false },
  },
})
export default function App() {
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <HashRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="conversations" element={<Conversations />} />
              <Route path="conversations/:id" element={<ConversationDetail />} />
              <Route path="evaluations/:id" element={<ConversationDetail evaluationRoute />} />
              <Route path="checklists" element={<Checklists />} />
              <Route path="checklists/:id" element={<Checklists />} />
              <Route path="appeals" element={<Appeals />} />
              <Route path="appeals/:id" element={<AppealDetail />} />
              <Route path="ai-jobs" element={<AIJobs />} />
              <Route path="ai-jobs/:id" element={<AIJobDetail />} />
              <Route path="ai-batches/:id" element={<AIBatchDetail />} />
              <Route path="datasets" element={<Datasets />} />
              <Route
                path="*"
                element={
                  <section>
                    <h1>Страница не найдена</h1>
                    <Link to="/">Вернуться к обзору</Link>
                  </section>
                }
              />
            </Route>
          </Routes>
        </HashRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}
