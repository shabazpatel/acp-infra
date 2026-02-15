from datetime import datetime, timezone

from acp_framework.models import (
    ACPAction,
    ACPActionEvent,
    ACPActor,
    ACPExecution,
    ACPExecutionStatus,
    ACPIntent,
    ACPIntentType,
    ACPVerification,
    CompareProductsRequest,
)


def test_compare_request_requires_minimum_two_ids():
    try:
        CompareProductsRequest(product_ids=["only_one"])
        assert False, "Expected CompareProductsRequest validation to fail"
    except Exception:
        pass


def test_acp_action_event_contract_builds_with_required_fields():
    event = ACPActionEvent(
        action_id="act_123",
        timestamp=datetime.now(timezone.utc),
        session_id="sess_123",
        actor=ACPActor(type="agent", id="commerce-assistant"),
        intent=ACPIntent(type=ACPIntentType.SEARCH, confidence=0.95, user_utterance="find sofas"),
        action=ACPAction(
            type=ACPIntentType.SEARCH,
            input={"q": "sofa"},
            idempotency_key="search_abc",
        ),
        verification=ACPVerification(schema_valid=True, approved=True),
        execution=ACPExecution(
            status=ACPExecutionStatus.SUCCEEDED,
            service="seller",
            latency_ms=25,
            result_ref="search",
        ),
    )

    dumped = event.model_dump(mode="json")
    assert dumped["intent"]["type"] == "search"
    assert dumped["execution"]["status"] == "succeeded"
    assert dumped["verification"]["approved"] is True
