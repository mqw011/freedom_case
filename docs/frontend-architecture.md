# Frontend architecture

## Компоненты и данные

React 19 + Vite 8 + JavaScript + React Router 7/HashRouter. Fetch транспорт централизован в `src/api/client.js`, предметные модули — datasets, conversations, evaluations, checklists, appeals, ai. TanStack Query хранит server state только в памяти вкладки. Транскрипты не сохраняются в localStorage, analytics или console. React экранирует текст; `dangerouslySetInnerHTML` не используется. Иконки локальные lucide-react, шрифты системные, внешней telemetry нет.

`useWorkspace` загружает все страницы метаданных с API limit=100. Он не скачивает полные транскрипты: они запрашиваются при открытии карточки. Список не скрывает записи после первых 50/100; фильтры и агрегаты охватывают весь полученный набор. Это осознанный компромисс для хакатона с десятками/сотнями диалогов. При тысячах записей следующим шагом станет серверный агрегирующий endpoint с теми же правилами, а не подсчёт по первой странице.

`latestByConversation` выбирает последнюю completed evaluation по completed_at (при равенстве — ID). Average использует её `final_score`, исключая null. Последнее AI задание выбирается по created_at. Новая failed-задача не удаляет предыдущую успешную оценку. Decimal.js используется для форматирования, суммы весов и агрегата среднего; расчёт итоговой оценки и перераспределение N/A остаются только в Python Scoring Engine.

## Обновление и отмена

Query keys: workspace, conversation/ID, evaluation/ID, versions/checklistID, version-catalog, appeal/ID, job/ID, attempts/ID/status/attempts, batch/ID, health, ai-health. После успешной мутации все связанные запросы инвалидируются. Конфликт 409 также обновляет server state. Fetch использует AbortController через сигнал Query, timeout, безопасные ошибки. Мутации автоматически не повторяются; AI creation имеет idempotency key на выбранный payload в открытой форме.

При queued/running заданиях workspace обновляется раз в 5 секунд; карточка job — раз в 4 секунды, batch — раз в 5. После terminal status polling останавливается, фоновые вкладки не опрашиваются. Health проверяется отдельно раз в 15 секунд. React Query снимает подписки и отменяет незавершённые запросы при уходе со страницы; stale time 10 секунд. Метаданные jobs загружаются до evaluations, чтобы завершившееся задание не опередило получение связанной оценки в том же цикле.

## Навигация

`/#/`, `/#/conversations`, `/#/conversations/:id`, `/#/evaluations/:id`, `/#/checklists`, `/#/checklists/:id`, `/#/appeals`, `/#/appeals/:id`, `/#/ai-jobs`, `/#/ai-jobs/:id`, `/#/ai-batches/:id`, `/#/datasets`.

Фильтры и pagination списка сохраняются в query string внутри hash. Back возвращает прежний набор. История оценок закрепляет конкретный evaluation ID; его версия чек-листа используется для ответов и reviewer form, независимо от текущей активной версии.

## Evidence

ID сообщения сопоставляется с настоящими `Message.id`. Диапазон строится по порядку массива транскрипта, не по арифметике ID. Quote выделяет точную подстроку; range/absence выделяют проверенные сообщения, отсутствие границ у absence обозначает весь разговор. Неверный ID, перевёрнутый диапазон или отсутствующая цитата показывают ошибку. Скролл и focus перемещаются к первому сообщению диапазона; текст не вставляется как HTML.

## UI и доступность

CSS tokens в `styles/tokens.css`, общие стили в `style.css`. `components/ui` содержит формы с label/description, кнопки, таблицы с локальным overflow, pagination, badges, skeleton/error/empty, native dialog с фокусом и Escape, вкладки с клавиатурными стрелками, toast и progress. Боковое меню на mobile управляется с клавиатуры; закрытая навигация не попадает в Tab. Reduced-motion отключает анимации. Основные размеры: 1440, 1280, 768, 390.

Frontend не выдаёт completed без backend-ответа. Никакой отдельной «демо-бизнес-логики» в production нет: `VITE_DEMO_MODE` добавляет только баннер, а синтетические данные создаёт отдельный developer server.

Accessibility regression использует axe-core через [официальный Playwright workflow](https://playwright.dev/docs/accessibility-testing); автоматические проверки дополняют, но не заменяют ручную проверку клавиатуры и визуальный аудит.
