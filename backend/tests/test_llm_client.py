"""Корпоративная LLM: отключена без настроек, работает через подменный транспорт.

Сеть в автотестах не нужна: httpx.MockTransport имитирует OpenAI-совместимый
шлюз. Проверяется и главное правило модуля — вердикты и числа в модель
передаются готовыми, а системная инструкция с ограничениями добавляется всегда.
"""

import json

import httpx
from fastapi.testclient import TestClient

from app.llm_client import SYSTEM_GUARDRAILS, LlmClient, LlmNotConfigured, LlmSettings, explain_selection
from app.main import app

client = TestClient(app)


def _settings() -> LlmSettings:
    return LlmSettings(base_url='https://llm.test/v1', api_key='secret', model='corp-model', timeout_s=5)


def test_client_is_disabled_without_configuration(monkeypatch):
    for name in ('GASMETER_LLM_BASE_URL', 'GASMETER_LLM_API_KEY', 'GASMETER_LLM_MODEL'):
        monkeypatch.delenv(name, raising=False)
    llm = LlmClient()
    status = llm.status()
    assert status.configured is False
    assert 'не подключена' in status.detail
    try:
        llm.chat([{'role': 'user', 'content': 'привет'}])
    except LlmNotConfigured:
        pass
    else:
        raise AssertionError('без настроек chat обязан отказать явно')


def test_chat_sends_guardrails_and_bearer_and_parses_reply():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen['url'] = str(request.url)
        seen['auth'] = request.headers.get('authorization')
        seen['body'] = json.loads(request.content)
        return httpx.Response(200, json={
            'model': 'corp-model-v2',
            'choices': [{'message': {'role': 'assistant', 'content': '  Ответ модели  '}}],
            'usage': {'prompt_tokens': 42, 'completion_tokens': 7},
        })

    llm = LlmClient(_settings(), transport=httpx.MockTransport(handler))
    reply = llm.chat([{'role': 'user', 'content': 'Объясни вердикт'}])

    assert seen['url'] == 'https://llm.test/v1/chat/completions'
    assert seen['auth'] == 'Bearer secret'
    assert seen['body']['model'] == 'corp-model'
    assert seen['body']['messages'][0] == {'role': 'system', 'content': SYSTEM_GUARDRAILS}
    assert seen['body']['messages'][1]['content'] == 'Объясни вердикт'
    assert reply.text == 'Ответ модели'
    assert reply.model == 'corp-model-v2'
    assert reply.prompt_tokens == 42


def test_status_probe_reports_unreachable_gateway():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('refused', request=request)

    status = LlmClient(_settings(), transport=httpx.MockTransport(handler)).status()
    assert status.configured is True
    assert status.reachable is False
    assert 'недоступн' in status.detail


def test_explain_selection_passes_facts_verbatim_and_forbids_recalculation():
    prompts = []

    def handler(request: httpx.Request) -> httpx.Response:
        prompts.append(json.loads(request.content)['messages'][-1]['content'])
        return httpx.Response(200, json={'choices': [{'message': {'content': 'ок'}}]})

    selection = {
        'best_method': {
            'verdict_title': 'Подходит', 'registration_number': '0169.RA.RU.314369/2024',
            'title': 'Методика ДРГ.М-1600', 'reasons': ['Расход внутри диапазона МИ 40–1600 м³/ч'],
        },
        'technologist_advice': ['Принять нижний расход 80 м³/ч'],
        'ranges': [{'label': 'Расход при рабочих условиях', 'q_min': 60, 'q_max': 325, 'unit': 'м³/ч'}],
        'summary': 'Рекомендуется 0169.RA.RU.314369/2024',
    }
    explain_selection(LlmClient(_settings(), transport=httpx.MockTransport(handler)), selection, 'kip')

    prompt = prompts[0]
    assert '0169.RA.RU.314369/2024' in prompt
    assert '40–1600' in prompt
    assert 'Принять нижний расход 80 м³/ч' in prompt
    assert 'не пересчитывай' in prompt
    assert 'КИПиА' in prompt


def test_status_endpoint_never_leaks_api_key(monkeypatch):
    monkeypatch.setenv('GASMETER_LLM_BASE_URL', 'https://llm.test/v1')
    monkeypatch.setenv('GASMETER_LLM_API_KEY', 'super-secret-key')
    monkeypatch.setenv('GASMETER_LLM_MODEL', 'corp-model')
    response = client.get('/api/llm/status')
    assert response.status_code == 200
    body = response.json()
    assert body['configured'] is True
    assert 'super-secret-key' not in response.text
    assert body['usage_policy']


def test_explain_endpoint_returns_503_when_llm_not_configured(monkeypatch):
    for name in ('GASMETER_LLM_BASE_URL', 'GASMETER_LLM_API_KEY', 'GASMETER_LLM_MODEL'):
        monkeypatch.delenv(name, raising=False)
    response = client.post('/api/llm/explain-selection', json={'selection': {'summary': 'x'}, 'audience': 'technologist'})
    assert response.status_code == 503


def test_ollama_protocol_uses_api_chat_without_stream_or_think():
    """Корпоративная LLM — Ollama: родной /api/chat, stream=false, think=false, num_predict."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen['url'] = str(request.url)
        seen['body'] = json.loads(request.content)
        return httpx.Response(200, json={
            'model': 'gemma4:e4b',
            'message': {'role': 'assistant', 'content': 'Методика подходит для режима.'},
            'prompt_eval_count': 120, 'eval_count': 18,
        })

    settings = LlmSettings(base_url='http://10.61.157.1:11434', api_key=None, model='gemma4:e4b', timeout_s=5)
    assert settings.is_ollama
    reply = LlmClient(settings, transport=httpx.MockTransport(handler)).chat([{'role': 'user', 'content': 'Объясни'}])

    assert seen['url'] == 'http://10.61.157.1:11434/api/chat'
    assert seen['body']['stream'] is False
    assert seen['body']['think'] is False
    assert seen['body']['options']['num_predict'] > 0
    assert seen['body']['messages'][0]['role'] == 'system'
    assert reply.text == 'Методика подходит для режима.'
    assert reply.prompt_tokens == 120


def test_ollama_status_probes_api_version():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == '/api/version'
        return httpx.Response(200, json={'version': '0.24.0'})

    settings = LlmSettings(base_url='http://10.61.157.1:11434', api_key=None, model='gemma4:e4b', timeout_s=5)
    status = LlmClient(settings, transport=httpx.MockTransport(handler)).status()
    assert status.reachable is True
    assert '0.24.0' in status.detail


def test_critic_rejects_numbers_absent_from_facts():
    from app.llm_client import criticize

    facts = 'диапазон МИ 40–1600 м³/ч; давление 0,5 МПа'
    kept, notes = criticize('Диапазон 40–1600 м³/ч при 0.5 МПа подходит, две линии не нужны.', facts)
    assert kept and not notes

    dropped, notes = criticize('Пересчитанный расход 1734 м³/ч укладывается в 40–1600.', facts)
    assert dropped == ''
    assert notes and '1734' in notes[0]


def test_explain_selection_drops_reply_with_invented_numbers():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Рекомендую принять 4321 м³/ч.'}}]})

    selection = {'best_method': {'verdict_title': 'Подходит', 'registration_number': '0169.RA.RU.314369/2024', 'reasons': ['Расход 60–325 м³/ч внутри МИ']}}
    reply = explain_selection(LlmClient(_settings(), transport=httpx.MockTransport(handler)), selection)
    assert reply.text == ''
    assert reply.notes and 'критик' in reply.notes[0]
