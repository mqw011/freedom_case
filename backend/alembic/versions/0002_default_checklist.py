"""Seed the immutable original Freedom Broker checklist.

Revision ID: 0002_default_checklist
Revises: 619a995632a7
"""

import json
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0002_default_checklist"
down_revision = "619a995632a7"
branch_labels = None
depends_on = None

SNAPSHOT = json.loads(r"""
{
  "name": "Freedom Broker",
  "description": "Исходный чек-лист CQA: 8 критериев.",
  "version": {
    "criteria": [
      {
        "code": "01",
        "title": "Установление контакта",
        "description": "Оператор поздоровался на языке клиента и представился в первом ответе. Для «Да» должны быть выполнены оба условия. Да = 10 баллов, Нет = 0. N/A не разрешён.",
        "section": "Начало и понимание запроса",
        "criterion_type": "binary",
        "weight": "10",
        "allowed_values": [
          "0",
          "1"
        ],
        "max_score": "1",
        "allow_na": false,
        "na_condition": null,
        "scale_labels": {},
        "display_order": 1
      },
      {
        "code": "02",
        "title": "Выявление потребности",
        "description": "Да: оператор учёл уже известные детали и уточнил недостающие до ответа. Нет: действие требовалось, но не было выполнено корректно.",
        "section": "Начало и понимание запроса",
        "criterion_type": "binary",
        "weight": "15",
        "allowed_values": [
          "0",
          "1"
        ],
        "max_score": "1",
        "allow_na": true,
        "na_condition": "Данных для ответа хватало с самого начала.",
        "scale_labels": {},
        "display_order": 2
      },
      {
        "code": "03",
        "title": "Идентификация",
        "description": "Да: проверка личности подтверждена до раскрытия защищённых данных или выполнения защищённого действия. Нет: идентификация требовалась, но не подтверждена до защищённого действия. Общий вопрос о тарифах сам по себе не требует идентификации.",
        "section": "Безопасность и решение",
        "criterion_type": "binary",
        "weight": "20",
        "allowed_values": [
          "0",
          "1"
        ],
        "max_score": "1",
        "allow_na": true,
        "na_condition": "Запрос не требовал идентификации.",
        "scale_labels": {},
        "display_order": 3
      },
      {
        "code": "04",
        "title": "Корректная и полная консультация",
        "description": "Оценка полноты и корректности консультации по дискретной шкале. Промежуточные значения запрещены.",
        "section": "Безопасность и решение",
        "criterion_type": "scale",
        "weight": "20",
        "allowed_values": [
          "0",
          "5",
          "10",
          "15",
          "20"
        ],
        "max_score": "20",
        "allow_na": true,
        "na_condition": "Чат закончился до того, как клиент сформулировал запрос.",
        "scale_labels": {
          "20": "Все существенные вопросы закрыты или дан корректный следующий шаг.",
          "15": "Основной вопрос решён, пропущена второстепенная деталь.",
          "10": "Часть запроса закрыта, существенный вопрос остался открытым.",
          "5": "Есть общая подсказка, но клиенту всё ещё непонятно, как действовать.",
          "0": "Ответа по существу нет или ключевая рекомендация ошибочна."
        },
        "display_order": 4
      },
      {
        "code": "05",
        "title": "Эмпатия и клиентоориентированность",
        "description": "Да: оператор вежлив и, если клиент выразил недовольство либо описал неудобство, отреагировал на конкретную проблему. N/A не разрешён.",
        "section": "Ведение и завершение диалога",
        "criterion_type": "binary",
        "weight": "15",
        "allowed_values": [
          "0",
          "1"
        ],
        "max_score": "1",
        "allow_na": false,
        "na_condition": null,
        "scale_labels": {},
        "display_order": 5
      },
      {
        "code": "06",
        "title": "Управление диалогом, скорость и грамотность",
        "description": "Шкала 0–10 переводится в вес 15. Порог первой реакции в 3 минуты не учитывается. Самостоятельного штрафа за ответ дольше трёх минут нет. Теги и вложения не оцениваются. N/A не разрешён.",
        "section": "Ведение и завершение диалога",
        "criterion_type": "scale",
        "weight": "15",
        "allowed_values": [
          "0",
          "4",
          "7",
          "10"
        ],
        "max_score": "10",
        "allow_na": false,
        "na_condition": null,
        "scale_labels": {
          "10": "Ответы ясные и связные; если было явное ожидание, оператор предупредил.",
          "7": "Один заметный сбой, но клиент может понять ответ и продолжить.",
          "4": "Клиенту приходится переспрашивать из-за формулировок или порядка ответов.",
          "0": "Из-за бессвязных или противоречивых реплик ход диалога непонятен."
        },
        "display_order": 6
      },
      {
        "code": "07",
        "title": "Завершение",
        "description": "Да: оператор подвёл итог или предложил дальнейшую помощь и попрощался.",
        "section": "Ведение и завершение диалога",
        "criterion_type": "binary",
        "weight": "5",
        "allowed_values": [
          "0",
          "1"
        ],
        "max_score": "1",
        "allow_na": true,
        "na_condition": "Чат оборвался до возможности завершить его.",
        "scale_labels": {},
        "display_order": 7
      },
      {
        "code": "08",
        "title": "Грубые ошибки",
        "description": "Да при любом нарушении: оскорбление клиента; предложение платной услуги в обход компании; раскрытие конфиденциальной информации. Пример обхода компании: предложение перевести деньги оператору лично для инвестирования или просьба дать личный номер для платной консультации в частном порядке. Самого предложения достаточно: согласие клиента и реальный перевод не требуются. Флаг не участвует в сумме 100 баллов и не обнуляет общую оценку.",
        "section": "Грубые нарушения",
        "criterion_type": "flag",
        "weight": "0",
        "allowed_values": [
          "0",
          "1"
        ],
        "max_score": "1",
        "allow_na": false,
        "na_condition": null,
        "scale_labels": {},
        "display_order": 8
      }
    ]
  }
}
""")


def upgrade():
    bind = op.get_bind()
    now = datetime.now(UTC)
    checklist = sa.table(
        "checklists",
        sa.column("id", sa.Integer),
        sa.column("seed_key"),
        sa.column("name"),
        sa.column("description"),
        sa.column("active_version_id", sa.Integer),
        sa.column("revision", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    version = sa.table(
        "checklist_versions",
        sa.column("id", sa.Integer),
        sa.column("checklist_id", sa.Integer),
        sa.column("version_number", sa.Integer),
        sa.column("status"),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    criterion = sa.table(
        "criteria",
        sa.column("checklist_version_id", sa.Integer),
        *[
            sa.column(name)
            for name in (
                "code",
                "title",
                "description",
                "section",
                "criterion_type",
                "weight",
                "max_score",
                "na_condition",
            )
        ],
        sa.column("allowed_values", sa.JSON),
        sa.column("scale_labels", sa.JSON),
        sa.column("allow_na", sa.Boolean),
        sa.column("display_order", sa.Integer),
    )
    checklist_id = bind.execute(
        checklist.insert()
        .values(
            seed_key="freedom-broker-original-v1",
            name=SNAPSHOT["name"],
            description=SNAPSHOT["description"],
            created_at=now,
            updated_at=now,
            revision=1,
        )
        .returning(checklist.c.id)
    ).scalar_one()
    version_id = bind.execute(
        version.insert()
        .values(checklist_id=checklist_id, version_number=1, status="published", created_at=now)
        .returning(version.c.id)
    ).scalar_one()
    bind.execute(
        criterion.insert(),
        [dict(c, checklist_version_id=version_id) for c in SNAPSHOT["version"]["criteria"]],
    )
    bind.execute(
        checklist.update()
        .where(checklist.c.id == checklist_id)
        .values(active_version_id=version_id)
    )


def downgrade():
    bind = op.get_bind()
    # This is a destructive development rollback; referenced evaluations prevent it via FKs.
    bind.execute(
        sa.text(
            "UPDATE checklists SET active_version_id = NULL "
            "WHERE seed_key = 'freedom-broker-original-v1'"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM criteria WHERE checklist_version_id IN "
            "(SELECT id FROM checklist_versions WHERE checklist_id IN "
            "(SELECT id FROM checklists WHERE seed_key = 'freedom-broker-original-v1'))"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM checklist_versions WHERE checklist_id IN "
            "(SELECT id FROM checklists WHERE seed_key = 'freedom-broker-original-v1')"
        )
    )
    bind.execute(sa.text("DELETE FROM checklists WHERE seed_key = 'freedom-broker-original-v1'"))
