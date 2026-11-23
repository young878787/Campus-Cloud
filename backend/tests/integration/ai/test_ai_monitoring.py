import uuid

from sqlmodel import Session, select

from app.core.db import engine


def test_failed_usage_record_leaves_session_usable(db: Session) -> None:
    """用量寫入失敗只記 log；同一個 session 之後的查詢不能被 PendingRollbackError 打壞。"""
    from app.ai.monitoring import record_ai_template_call

    with Session(engine) as session:
        # 不存在的 user_id 會觸發外鍵錯誤，模擬 commit 失敗
        record_ai_template_call(
            session=session,
            user_id=uuid.uuid4(),
            call_type="chat",
            model_name="test-model",
            metrics={"prompt_tokens": 1, "completion_tokens": 1},
        )

        assert session.exec(select(1)).one() == 1
