"""验证直调 agent 函数的 overrides 透传（拦截 get_default_chat_model 断言 ContextVar）。"""
import app.agents.code_reviewer as cr_module
import app.agents.code_tester as ct_module
from app.agents.llm import _current_overrides


def test_llm_review_code_sets_overrides_in_contextvar(monkeypatch):
    captured = {}

    class FakeModel:
        def invoke(self, messages):
            captured["ctx"] = _current_overrides.get()
            class Resp:
                content = ('{"logic_correctness":{"score":1,"issues":[]},'
                           '"security":{"score":1,"issues":[]},'
                           '"code_quality":{"score":1,"issues":[]},'
                           '"domain_compliance":{"score":1,"issues":[]}}')
            return Resp()

    monkeypatch.setattr(cr_module, "get_default_chat_model", lambda: FakeModel())

    overrides = {"api_key": "sk-r", "model": "rm"}
    cr_module.llm_review_code(
        code="x=1", target_direction="t", knowledge_nodes=[], llm_overrides=overrides,
    )
    assert captured.get("ctx") == overrides
    # 退出函数后 ContextVar reset
    assert _current_overrides.get() is None


def test_llm_generate_tests_sets_overrides_in_contextvar(monkeypatch):
    captured = {}

    class FakeModel:
        def invoke(self, messages):
            captured["ctx"] = _current_overrides.get()
            class Resp:
                content = "```python\ndef test_a(): assert 1\n```\n```json\n[]\n```"
            return Resp()

    monkeypatch.setattr(ct_module, "get_default_chat_model", lambda: FakeModel())

    overrides = {"api_key": "sk-t", "model": "tm"}
    try:
        ct_module.llm_generate_tests(
            entities=[], knowledge_nodes=[], target_direction="t",
            module_name="main", llm_overrides=overrides,
        )
    except Exception:
        pass
    assert captured.get("ctx") == overrides
    assert _current_overrides.get() is None
