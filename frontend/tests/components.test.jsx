import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../src/components/ui/Toast'
import { ErrorState, Field, Input, Modal, Tabs } from '../src/components/ui'
import TranscriptViewer from '../src/components/conversations/TranscriptViewer'
import AudioPlayer from '../src/components/conversations/AudioPlayer'
import EvaluationPanel from '../src/components/evaluations/EvaluationPanel'
import { ConversationTable } from '../src/pages/Conversations'
import { CriterionEditor } from '../src/pages/Checklists'
import { ReviewerDecision } from '../src/pages/AppealDetail'
import BatchCard from '../src/components/ai/BatchCard'
import { JobsTable } from '../src/pages/AIJobs'
import BackendStatus from '../src/components/BackendStatus'
import { useHealth } from '../src/hooks/data'
import { newCriterion } from '../src/utils/domain'
vi.mock('../src/hooks/data', async (importOriginal) => ({
  ...(await importOriginal()),
  useHealth: vi.fn(),
}))
function wrap(element) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter>
        <ToastProvider>{element}</ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
const messages = [
  {
    id: 41,
    message_index: 0,
    speaker: 'system',
    timestamp_raw: '00:00',
    text: 'Synthetic event',
  },
  {
    id: 42,
    message_index: 1,
    speaker: 'operator',
    timestamp_raw: '00:03',
    text: 'Сәлем!\nHello <script>alert(1)</script>',
  },
]
const criterion = {
  ...newCriterion(),
  id: 5,
  code: '03',
  title: 'Synthetic criterion',
  section: 'Test',
  description: 'Test',
  allow_na: true,
  na_condition: 'General question',
}
const result = {
  id: 9,
  criterion_id: 5,
  criterion_code: '03',
  answer: 'na',
  current_answer: 'na',
  current_is_na: true,
  explanation: 'Synthetic reason',
  current_weighted_score: null,
  evidence: [
    {
      id: 1,
      evidence_type: 'quote',
      message_id: 42,
      excerpt: 'Сәлем!',
      explanation: 'Exact quote',
    },
  ],
}
const evaluation = {
  id: 1,
  source: 'test',
  checklist_version_id: 1,
  initial_score: '81.88',
  final_score: '88.13',
  critical_violation: true,
  results: [result],
}
describe('Accessible UI primitives', () => {
  it('labels actual input', () => {
    wrap(
      <Field label="Example">
        <Input />
      </Field>,
    )
    expect(screen.getByLabelText('Example')).toBeVisible()
  })
  it('renders structured and non-array API details without crashing', () => {
    wrap(<ErrorState error={{ message: 'Conflict', details: { field: 'value' } }} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Conflict')
  })
  it('opens modal, restores focus and handles Escape', () => {
    const close = vi.fn()
    const trigger = document.createElement('button')
    document.body.append(trigger)
    trigger.focus()
    const view = wrap(
      <Modal title="Test dialog" onClose={close}>
        Body
      </Modal>,
    )
    expect(screen.getByRole('dialog')).toBeVisible()
    screen
      .getByRole('dialog')
      .dispatchEvent(new Event('cancel', { bubbles: true, cancelable: true }))
    expect(close).toHaveBeenCalled()
    view.unmount()
    expect(trigger).toHaveFocus()
    trigger.remove()
  })
  it('supports arrow keyboard navigation for tabs', async () => {
    function Test() {
      const [v, set] = useState('a')
      return (
        <Tabs
          value={v}
          onChange={set}
          options={[
            ['a', 'First'],
            ['b', 'Second'],
          ]}
        />
      )
    }
    wrap(<Test />)
    screen.getByRole('tab', { name: 'First' }).focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Second' })).toHaveAttribute('aria-selected', 'true')
  })
})
describe('Transcript and results', () => {
  it('preserves roles, timestamps, multilingual text and exact highlight without HTML injection', () => {
    const { container } = wrap(
      <TranscriptViewer
        messages={messages}
        selection={{ ids: [42], first: 42, excerpt: 'Сәлем!' }}
      />,
    )
    expect(screen.getByText('Система')).toBeVisible()
    expect(screen.getByText('00:03')).toBeVisible()
    expect(container.querySelector('mark')).toHaveTextContent('Сәлем!')
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('#message-42')).toHaveClass('highlighted')
  })
  it('navigates using evidence object and shows N/A, initial/final and critical flag', async () => {
    const select = vi.fn()
    wrap(
      <EvaluationPanel
        evaluation={evaluation}
        version={{ version_number: 1, criteria: [criterion] }}
        onEvidence={select}
      />,
    )
    expect(screen.getByText('Грубое нарушение подтверждено')).toBeVisible()
    expect(screen.getAllByText('N/A').length).toBeGreaterThan(0)
    expect(screen.getByText('81,88')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: /Цитата/ }))
    expect(select).toHaveBeenCalledWith(result.evidence[0])
  })
  it('opens appeal form and requires nonempty comment', async () => {
    wrap(
      <EvaluationPanel
        evaluation={evaluation}
        version={{ version_number: 1, criteria: [criterion] }}
        onEvidence={() => {}}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Оспорить оценку' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('button', { name: 'Подать апелляцию' })).toBeDisabled()
    await userEvent.type(within(dialog).getByLabelText('Причина несогласия'), 'Manual review')
    expect(within(dialog).getByRole('button', { name: 'Подать апелляцию' })).toBeEnabled()
  })
  it('renders safe audio fallback with no preload', () => {
    const { container } = wrap(<AudioPlayer url="https://example.invalid/test.wav" />)
    expect(container.querySelector('audio')).toHaveAttribute('preload', 'none')
    expect(screen.getByRole('link')).toHaveAttribute('rel', 'noopener noreferrer')
  })
  it('rejects unsafe audio scheme', () => {
    const { container } = wrap(<AudioPlayer url="javascript:alert(1)" />)
    expect(container.querySelector('audio')).toBeNull()
    expect(container.querySelector('a')).toBeNull()
  })
})
describe('Tables, editor and reviewer', () => {
  it('distinguishes failed job from valid score zero and unknown score', () => {
    wrap(
      <ConversationTable
        rows={[
          {
            id: 1,
            conversation_id: 'test-one',
            language: 'RU',
            channel: 'agent chat',
          },
          {
            id: 2,
            conversation_id: 'test-two',
            language: 'KZ',
            channel: 'voice call',
          },
        ]}
        selected={new Set()}
        onSelect={() => {}}
        datasets={[]}
        evaluations={new Map([[1, { id: 3, final_score: '0' }]])}
        jobs={new Map([[2, { id: 1, status: 'failed' }]])}
        onEvaluate={() => {}}
      />,
    )
    expect(screen.getByText('0')).toBeVisible()
    expect(screen.getByText('Не оценён')).toBeVisible()
    expect(screen.getByText('Ошибка')).toBeVisible()
  })
  it('converts flag to zero weight, no N/A', async () => {
    const change = vi.fn()
    wrap(
      <CriterionEditor
        criterion={criterion}
        index={0}
        count={1}
        onChange={change}
        onRemove={() => {}}
        onMove={() => {}}
      />,
    )
    await userEvent.selectOptions(screen.getByLabelText('Тип'), 'flag')
    expect(change).toHaveBeenCalledWith(
      expect.objectContaining({
        weight: '0',
        allow_na: false,
        na_condition: null,
        criterion_type: 'flag',
      }),
    )
  })
  it('editor exposes scale steps, max and labels', () => {
    wrap(
      <CriterionEditor
        criterion={{
          ...criterion,
          criterion_type: 'scale',
          allowed_values: ['0', '5', '10'],
          max_score: '10',
        }}
        index={0}
        count={1}
        onChange={() => {}}
        onRemove={() => {}}
        onMove={() => {}}
      />,
    )
    expect(screen.getByLabelText(/Допустимые ступени/)).toHaveValue('0,5,10')
    expect(screen.getByLabelText('Максимум шкалы')).toHaveValue('10')
  })
  it('reviewer submits exact revised answer with mandatory reason', async () => {
    const submit = vi.fn()
    wrap(
      <ReviewerDecision
        appeal={{ status: 'pending' }}
        result={result}
        criterion={criterion}
        onSubmit={submit}
      />,
    )
    expect(screen.getByRole('button', { name: 'Сохранить решение' })).toBeDisabled()
    await userEvent.selectOptions(screen.getByLabelText('Решение'), 'revised')
    await userEvent.selectOptions(screen.getByLabelText('Новый ответ'), 'yes')
    await userEvent.type(screen.getByLabelText('Причина решения'), 'Verified')
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить решение' }))
    expect(submit).toHaveBeenCalledWith({
      decision: 'revised',
      revised_answer: 'yes',
      reason: 'Verified',
    })
  })
  it('100% batch termination is not 100% success', () => {
    wrap(
      <BatchCard
        batch={{
          id: 1,
          percentage: '100',
          total: 2,
          completed: 0,
          failed: 1,
          cancelled: 1,
          queued: 0,
          running: 0,
          checklist_version_id: 1,
        }}
      />,
    )
    expect(screen.getByText(/Успешных оценок: 0 из 2/)).toBeVisible()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
  })
  it('jobs show attempts and failure without inventing score', () => {
    wrap(
      <JobsTable
        jobs={[
          {
            id: 5,
            conversation_id: 2,
            checklist_version_id: 1,
            model: 'test-model',
            provider: 'ollama',
            status: 'failed',
            attempts: 2,
            max_attempts: 2,
            error_code: 'provider_timeout',
          },
        ]}
        conversations={[]}
      />,
    )
    expect(screen.getByText('provider_timeout')).toBeVisible()
    expect(screen.getByText('Ошибка')).toBeVisible()
    expect(screen.queryByText('/ 100')).not.toBeInTheDocument()
  })
  it('separately identifies backend, provider and worker', () => {
    useHealth.mockReturnValue({
      backend: { isSuccess: true },
      ai: {
        data: { provider: { available: false }, worker: { available: false } },
      },
    })
    wrap(<BackendStatus />)
    const status = screen.getByLabelText('Состояние сервисов')
    expect(status).toHaveTextContent('Backend Online')
    expect(status).toHaveTextContent('LLM provider Недоступен')
    expect(status).toHaveTextContent('AI Worker Offline')
  })
})
