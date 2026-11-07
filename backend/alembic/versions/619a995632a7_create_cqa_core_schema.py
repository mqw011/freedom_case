"""create CQA core schema

Revision ID: 619a995632a7
Revises:
"""

import sqlalchemy as sa

from alembic import op

revision = "619a995632a7"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "checklists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("seed_key", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("active_version_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["active_version_id"],
            ["checklist_versions.id"],
            name="fk_checklist_active_version",
            use_alter=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seed_key"),
    )
    op.create_table(
        "checklist_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("checklist_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version_number > 0"),
        sa.ForeignKeyConstraint(
            ["checklist_id"],
            ["checklists.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checklist_id", "version_number"),
    )
    with op.batch_alter_table("checklist_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_checklist_versions_checklist_id"), ["checklist_id"], unique=False
        )

    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_records", sa.Integer(), nullable=False),
        sa.Column("import_status", sa.String(length=30), nullable=False),
        sa.CheckConstraint("total_records >= 0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id"),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=200), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("audio_url", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("channel IN ('agent chat', 'voice call')"),
        sa.CheckConstraint("language IN ('RU', 'KZ', 'EN')"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "conversation_id"),
    )
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_conversations_channel"), ["channel"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_conversations_conversation_id"), ["conversation_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_conversations_dataset_id"), ["dataset_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_conversations_language"), ["language"], unique=False)

    op.create_table(
        "criteria",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("checklist_version_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("section", sa.String(length=300), nullable=False),
        sa.Column("criterion_type", sa.String(length=20), nullable=False),
        sa.Column("weight", sa.String(length=100), nullable=False),
        sa.Column("allowed_values", sa.JSON(), nullable=False),
        sa.Column("max_score", sa.String(length=100), nullable=False),
        sa.Column("allow_na", sa.Boolean(), nullable=False),
        sa.Column("na_condition", sa.Text(), nullable=True),
        sa.Column("scale_labels", sa.JSON(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("criterion_type IN ('binary', 'scale', 'flag')"),
        sa.CheckConstraint("display_order >= 0"),
        sa.ForeignKeyConstraint(
            ["checklist_version_id"],
            ["checklist_versions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checklist_version_id", "code"),
        sa.UniqueConstraint("checklist_version_id", "display_order"),
    )
    with op.batch_alter_table("criteria", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_criteria_checklist_version_id"), ["checklist_version_id"], unique=False
        )

    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("checklist_version_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("initial_score", sa.String(length=100), nullable=True),
        sa.Column("final_score", sa.String(length=100), nullable=True),
        sa.Column("initial_critical_violation", sa.Boolean(), nullable=False),
        sa.Column("critical_violation", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("source IN ('manual', 'test', 'ai')"),
        sa.ForeignKeyConstraint(
            ["checklist_version_id"],
            ["checklist_versions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("evaluations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_evaluations_checklist_version_id"),
            ["checklist_version_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_evaluations_conversation_id"), ["conversation_id"], unique=False
        )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("message_index", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=20), nullable=False),
        sa.Column("timestamp_raw", sa.String(length=100), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint("speaker IN ('client', 'operator', 'bot', 'system')"),
        sa.CheckConstraint("message_index >= 0"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "message_index"),
    )
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_messages_conversation_id"), ["conversation_id"], unique=False
        )

    op.create_table(
        "criterion_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluation_id", sa.Integer(), nullable=False),
        sa.Column("criterion_id", sa.Integer(), nullable=False),
        sa.Column("answer", sa.String(length=100), nullable=False),
        sa.Column("raw_score", sa.String(length=100), nullable=True),
        sa.Column("weighted_score", sa.String(length=100), nullable=True),
        sa.Column("is_na", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["criterion_id"],
            ["criteria.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_id", "criterion_id"),
    )
    with op.batch_alter_table("criterion_results", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_criterion_results_criterion_id"), ["criterion_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_criterion_results_evaluation_id"), ["evaluation_id"], unique=False
        )

    op.create_table(
        "appeals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluation_id", sa.Integer(), nullable=False),
        sa.Column("criterion_result_id", sa.Integer(), nullable=False),
        sa.Column("pending_result_id", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(status = 'pending' AND pending_result_id = criterion_result_id "
            "AND pending_result_id IS NOT NULL) OR "
            "(status != 'pending' AND pending_result_id IS NULL)"
        ),
        sa.CheckConstraint("status IN ('pending', 'upheld', 'revised')"),
        sa.ForeignKeyConstraint(
            ["criterion_result_id"],
            ["criterion_results.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["pending_result_id"],
            ["criterion_results.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pending_result_id"),
    )
    with op.batch_alter_table("appeals", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_appeals_criterion_result_id"), ["criterion_result_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_appeals_evaluation_id"), ["evaluation_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_appeals_status"), ["status"], unique=False)

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("criterion_result_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("end_message_id", sa.Integer(), nullable=True),
        sa.Column("evidence_type", sa.String(length=20), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.CheckConstraint("evidence_type IN ('quote', 'range', 'absence')"),
        sa.ForeignKeyConstraint(
            ["criterion_result_id"],
            ["criterion_results.id"],
        ),
        sa.ForeignKeyConstraint(
            ["end_message_id"],
            ["messages.id"],
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("evidence", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_evidence_criterion_result_id"), ["criterion_result_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_evidence_end_message_id"), ["end_message_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_evidence_message_id"), ["message_id"], unique=False)

    op.create_table(
        "appeal_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("appeal_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("original_answer", sa.String(length=100), nullable=False),
        sa.Column("revised_answer", sa.String(length=100), nullable=False),
        sa.Column("original_score", sa.String(length=100), nullable=True),
        sa.Column("revised_score", sa.String(length=100), nullable=True),
        sa.Column("original_final_score", sa.String(length=100), nullable=True),
        sa.Column("revised_final_score", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('upheld', 'revised')"),
        sa.ForeignKeyConstraint(
            ["appeal_id"],
            ["appeals.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appeal_id"),
    )

    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_checklist_active_version",
            "checklists",
            "checklist_versions",
            ["active_version_id"],
            ["id"],
        )


def downgrade():
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_checklist_active_version", "checklists", type_="foreignkey")
    op.drop_table("appeal_decisions")
    with op.batch_alter_table("evidence", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_evidence_message_id"))
        batch_op.drop_index(batch_op.f("ix_evidence_end_message_id"))
        batch_op.drop_index(batch_op.f("ix_evidence_criterion_result_id"))

    op.drop_table("evidence")
    with op.batch_alter_table("appeals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_appeals_status"))
        batch_op.drop_index(batch_op.f("ix_appeals_evaluation_id"))
        batch_op.drop_index(batch_op.f("ix_appeals_criterion_result_id"))

    op.drop_table("appeals")
    with op.batch_alter_table("criterion_results", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_criterion_results_evaluation_id"))
        batch_op.drop_index(batch_op.f("ix_criterion_results_criterion_id"))

    op.drop_table("criterion_results")
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_messages_conversation_id"))

    op.drop_table("messages")
    with op.batch_alter_table("evaluations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_evaluations_conversation_id"))
        batch_op.drop_index(batch_op.f("ix_evaluations_checklist_version_id"))

    op.drop_table("evaluations")
    with op.batch_alter_table("criteria", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_criteria_checklist_version_id"))

    op.drop_table("criteria")
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_conversations_language"))
        batch_op.drop_index(batch_op.f("ix_conversations_dataset_id"))
        batch_op.drop_index(batch_op.f("ix_conversations_conversation_id"))
        batch_op.drop_index(batch_op.f("ix_conversations_channel"))

    op.drop_table("conversations")
    op.drop_table("datasets")
    with op.batch_alter_table("checklist_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_checklist_versions_checklist_id"))

    op.drop_table("checklist_versions")
    op.drop_table("checklists")
