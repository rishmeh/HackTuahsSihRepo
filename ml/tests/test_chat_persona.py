"""
ml/tests/test_chat_persona.py — The chat pipeline actually uses the persona.

call_slm is replaced with a fake that records the system prompt it was given
and returns a canned answer, so these run without Ollama. What is under test
is the wiring: settings reach the prompt, the answer gets Tot's voice, and
students without a profile still get a safe default persona.

Run with: pytest ml/tests/test_chat_persona.py -v
"""

import pytest

from chat import pipeline
from chat.models import ChatRequest, SLMResponse, StudentProfile
from learner.profile_store import ProfileStore
from learner.questionnaire import load_questionnaire
from learner.scoring import score_answers
from persona.phrases import PhraseBook

RAW_ANSWER = "Plants make their food from sunlight, water and carbon dioxide."


@pytest.fixture
def anyio_backend():
    """Run async tests on asyncio only; trio is not installed."""
    return "asyncio"


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = ProfileStore(tmp_path / "learner.db")
    monkeypatch.setattr(pipeline, "_learner_store", lambda: s)
    return s


@pytest.fixture
def slm(monkeypatch):
    """Fake SLM: records the system prompt, answers confidently."""
    calls: dict = {}

    async def fake_call_slm(query, student, history=None, *, think=False, system_prompt=None):
        calls["system_prompt"] = system_prompt
        calls["think"] = think
        return SLMResponse(answer=RAW_ANSWER, escalate=False, confidence=0.95, reason=None)

    monkeypatch.setattr(pipeline, "call_slm", fake_call_slm)
    return calls


def _enrol(store, student_id, age, answers):
    q = load_questionnaire()
    store.save(student_id, score_answers(answers, age=age, questionnaire=q))


def _request(student_id=None, situation=None, age=12):
    kwargs = dict(
        query="How do plants make food?",
        student=StudentProfile(age=age, grade="6th"),
        session_id=None,
    )
    if student_id is not None:
        kwargs["student_id"] = student_id
    if situation is not None:
        kwargs["situation"] = situation
    return ChatRequest(**kwargs)


NARRATIVE_TEEN = {1: "A", 2: "A", 3: "B", 4: "A", 5: "A", 6: "D", 7: "B", 8: "D", 9: "D", 10: "D"}
TERSE_TEEN = {**NARRATIVE_TEEN, 10: "A"}
ANXIOUS_CHILD = {1: "C", 2: "C", 3: "D", 4: "B", 5: "D", 6: "A", 7: "A", 8: "A", 9: "C", 10: "C"}


class TestPromptWiring:
    @pytest.mark.anyio
    async def test_prompt_is_tot_not_kidbot(self, store, slm):
        _enrol(store, "asha", 14, NARRATIVE_TEEN)
        await pipeline.run_chat_pipeline(_request("asha"))
        assert "Tot" in slm["system_prompt"]
        assert "KidBot" not in slm["system_prompt"]

    @pytest.mark.anyio
    async def test_students_directives_reach_the_prompt(self, store, slm):
        _enrol(store, "asha", 14, NARRATIVE_TEEN)
        await pipeline.run_chat_pipeline(_request("asha"))
        prompt = slm["system_prompt"]
        assert "story" in prompt.lower()  # narrative directive

    @pytest.mark.anyio
    async def test_safety_rules_and_json_contract_survive(self, store, slm):
        _enrol(store, "asha", 14, NARRATIVE_TEEN)
        await pipeline.run_chat_pipeline(_request("asha"))
        prompt = slm["system_prompt"]
        assert "STRICT RULES" in prompt
        assert '"escalate"' in prompt
        assert prompt.index("Tot") < prompt.index("STRICT RULES")

    @pytest.mark.anyio
    async def test_prompt_never_asks_the_model_to_be_sarcastic(self, store, slm):
        _enrol(store, "asha", 14, NARRATIVE_TEEN)  # a student for whom sarcasm IS allowed
        await pipeline.run_chat_pipeline(_request("asha"))
        assert "sarcas" not in slm["system_prompt"].lower()


class TestAnswerDecoration:
    @pytest.mark.anyio
    async def test_answer_keeps_the_models_content(self, store, slm):
        _enrol(store, "asha", 14, NARRATIVE_TEEN)
        response = await pipeline.run_chat_pipeline(_request("asha"))
        assert RAW_ANSWER in response.answer
        assert response.source == "slm"

    @pytest.mark.anyio
    async def test_answer_gets_tots_voice(self, store, slm):
        _enrol(store, "asha", 14, NARRATIVE_TEEN)
        response = await pipeline.run_chat_pipeline(_request("asha"))
        assert response.answer != RAW_ANSWER

    @pytest.mark.anyio
    async def test_terse_students_get_the_bare_answer(self, store, slm):
        _enrol(store, "quick", 14, TERSE_TEEN)
        response = await pipeline.run_chat_pipeline(_request("quick"))
        assert response.answer == RAW_ANSWER

    @pytest.mark.anyio
    async def test_wrong_answer_situation_uses_the_students_style(self, store, slm):
        _enrol(store, "ravi", 9, ANXIOUS_CHILD)
        response = await pipeline.run_chat_pipeline(_request("ravi", situation="wrong_answer"))
        opener = response.answer.replace(RAW_ANSWER, "").strip()
        # The opener must be one of the gentle lines and never a sarcastic one.
        from persona.phrases import _WRONG_ANSWER  # test-only peek at the pool

        assert opener in _WRONG_ANSWER["gentle"]


class TestFallbackPersona:
    """A student without a profile still meets Tot — the safe default Tot."""

    @pytest.mark.anyio
    async def test_unknown_student_gets_default_persona(self, store, slm):
        response = await pipeline.run_chat_pipeline(_request("stranger"))
        assert "Tot" in slm["system_prompt"]
        assert RAW_ANSWER in response.answer

    @pytest.mark.anyio
    async def test_no_student_id_gets_default_persona(self, store, slm):
        response = await pipeline.run_chat_pipeline(_request())
        assert "Tot" in slm["system_prompt"]
        assert RAW_ANSWER in response.answer

    @pytest.mark.anyio
    async def test_default_persona_never_uses_sarcasm(self, store, slm):
        for situation in ("repeated_question", "idle", "question"):
            for _ in range(20):
                response = await pipeline.run_chat_pipeline(_request(situation=situation))
                extra = response.answer.replace(RAW_ANSWER, "").strip()
                for line in extra.splitlines():
                    assert not PhraseBook.is_sarcastic(line.strip()), (situation, line)


class TestRequestModel:
    def test_student_id_and_situation_are_optional(self):
        request = ChatRequest(query="hi", student=StudentProfile(age=10))
        assert request.student_id is None
        assert request.situation == "question"

    def test_unknown_situation_is_rejected(self):
        with pytest.raises(ValueError):
            ChatRequest(query="hi", student=StudentProfile(age=10), situation="dancing")
