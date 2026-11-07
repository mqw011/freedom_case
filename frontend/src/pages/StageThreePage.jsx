const pages = {
  conversations: ['Диалоги', 'Список, фильтры, транскрипт и аудиоплеер.'],
  details: ['Детали диалога', 'Критерии оценки и подтверждающие реплики.'],
  checklist: ['Чек-листы', 'Редактор критериев и управление версиями.'],
  appeals: ['Апелляции', 'Подача апелляций и решения проверяющего.'],
}

export default function StageThreePage({ page }) {
  const [title, description] = pages[page]
  return <section>
    <p className="eyebrow">ИНТЕРФЕЙС / ЭТАП 3</p>
    <h1>{title}</h1>
    <p className="lead">{description}</p>
    <p className="stage-note">Место для будущей страницы. Соответствующие backend-операции доступны через REST API и Swagger.</p>
  </section>
}
