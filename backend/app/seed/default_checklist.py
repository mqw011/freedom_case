"""Exact initial Freedom Broker rubric supplied in the Stage 1 specification."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import build_engine
from app.models import Checklist
from app.schemas.checklists import ChecklistCreate, CriterionConfig, VersionCreate
from app.services.checklist_service import ChecklistService

SEED_KEY = "freedom-broker-original-v1"


def default_checklist() -> ChecklistCreate:
    def criterion(
        code, title, section, weight, description, *, values=None, na=None, labels=None, flag=False
    ):
        return CriterionConfig(
            code=code,
            title=title,
            section=section,
            weight=weight,
            description=description,
            criterion_type="flag" if flag else "scale" if values else "binary",
            allowed_values=values or [0, 1],
            max_score=max(values) if values else 1,
            allow_na=na is not None,
            na_condition=na,
            scale_labels=labels or {},
            display_order=int(code),
        )

    beginning = "Начало и понимание запроса"
    solution = "Безопасность и решение"
    dialogue = "Ведение и завершение диалога"
    criteria = [
        criterion(
            "01",
            "Установление контакта",
            beginning,
            10,
            "Оператор поздоровался на языке клиента и представился в первом ответе. Для «Да» должны быть выполнены оба условия. Да = 10 баллов, Нет = 0. N/A не разрешён.",
        ),
        criterion(
            "02",
            "Выявление потребности",
            beginning,
            15,
            "Да: оператор учёл уже известные детали и уточнил недостающие до ответа. Нет: действие требовалось, но не было выполнено корректно.",
            na="Данных для ответа хватало с самого начала.",
        ),
        criterion(
            "03",
            "Идентификация",
            solution,
            20,
            "Да: проверка личности подтверждена до раскрытия защищённых данных или выполнения защищённого действия. Нет: идентификация требовалась, но не подтверждена до защищённого действия. Общий вопрос о тарифах сам по себе не требует идентификации.",
            na="Запрос не требовал идентификации.",
        ),
        criterion(
            "04",
            "Корректная и полная консультация",
            solution,
            20,
            "Оценка полноты и корректности консультации по дискретной шкале. Промежуточные значения запрещены.",
            values=[0, 5, 10, 15, 20],
            na="Чат закончился до того, как клиент сформулировал запрос.",
            labels={
                "20": "Все существенные вопросы закрыты или дан корректный следующий шаг.",
                "15": "Основной вопрос решён, пропущена второстепенная деталь.",
                "10": "Часть запроса закрыта, существенный вопрос остался открытым.",
                "5": "Есть общая подсказка, но клиенту всё ещё непонятно, как действовать.",
                "0": "Ответа по существу нет или ключевая рекомендация ошибочна.",
            },
        ),
        criterion(
            "05",
            "Эмпатия и клиентоориентированность",
            dialogue,
            15,
            "Да: оператор вежлив и, если клиент выразил недовольство либо описал неудобство, отреагировал на конкретную проблему. N/A не разрешён.",
        ),
        criterion(
            "06",
            "Управление диалогом, скорость и грамотность",
            dialogue,
            15,
            "Шкала 0–10 переводится в вес 15. Порог первой реакции в 3 минуты не учитывается. Самостоятельного штрафа за ответ дольше трёх минут нет. Теги и вложения не оцениваются. N/A не разрешён.",
            values=[0, 4, 7, 10],
            labels={
                "10": "Ответы ясные и связные; если было явное ожидание, оператор предупредил.",
                "7": "Один заметный сбой, но клиент может понять ответ и продолжить.",
                "4": "Клиенту приходится переспрашивать из-за формулировок или порядка ответов.",
                "0": "Из-за бессвязных или противоречивых реплик ход диалога непонятен.",
            },
        ),
        criterion(
            "07",
            "Завершение",
            dialogue,
            5,
            "Да: оператор подвёл итог или предложил дальнейшую помощь и попрощался.",
            na="Чат оборвался до возможности завершить его.",
        ),
        criterion(
            "08",
            "Грубые ошибки",
            "Грубые нарушения",
            0,
            "Да при любом нарушении: оскорбление клиента; предложение платной услуги в обход компании; раскрытие конфиденциальной информации. Пример обхода компании: предложение перевести деньги оператору лично для инвестирования или просьба дать личный номер для платной консультации в частном порядке. Самого предложения достаточно: согласие клиента и реальный перевод не требуются. Флаг не участвует в сумме 100 баллов и не обнуляет общую оценку.",
            flag=True,
        ),
    ]
    return ChecklistCreate(
        name="Freedom Broker",
        description="Исходный чек-лист CQA: 8 критериев.",
        version=VersionCreate(criteria=criteria),
    )


def ensure_default(session: Session) -> Checklist:
    existing = session.scalar(select(Checklist).where(Checklist.seed_key == SEED_KEY))
    return existing or ChecklistService(session).create(default_checklist(), seed_key=SEED_KEY)


def main():
    engine = build_engine(get_settings().database_url)
    with Session(engine) as session, session.begin():
        checklist = ensure_default(session)
        print(f"Checklist {checklist.id}, active version {checklist.active_version_id}")
    engine.dispose()


if __name__ == "__main__":
    main()
