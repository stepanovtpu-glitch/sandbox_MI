import httpx

from app import metrology_expert
from app.llm_client import LlmClient, LlmSettings


def test_source_search_remains_useful_without_model(monkeypatch, tmp_path):
    monkeypatch.setattr(metrology_expert, '_corpus_dir', lambda: tmp_path)
    monkeypatch.setattr(metrology_expert, '_database_ocr_sources', lambda: [])
    monkeypatch.delenv('GASMETER_LLM_BASE_URL', raising=False)
    monkeypatch.delenv('GASMETER_LLM_MODEL', raising=False)
    (tmp_path / 'МИ-расходомер.txt').write_text('Для расходомера указан рабочий диапазон давления от 0,1 до 5 МПа.', encoding='utf-8')
    answer = metrology_expert.answer_question('диапазон давления расходомера')
    assert answer.model == 'поиск по МИ без LLM'
    assert answer.sources[0]['review_state'] == 'unverified'
    assert '0,1 до 5 МПа' in answer.sources[0]['excerpt']
    assert 'не ответ или метрологическое заключение' in answer.text


def test_unreachable_model_returns_source_fragments(monkeypatch, tmp_path):
    monkeypatch.setattr(metrology_expert, '_corpus_dir', lambda: tmp_path)
    monkeypatch.setattr(metrology_expert, '_database_ocr_sources', lambda: [])
    (tmp_path / 'МИ-давление.txt').write_text('Ограничение по давлению указано в методике измерений.', encoding='utf-8')

    def fail(request):
        raise httpx.ConnectTimeout('offline')

    settings = LlmSettings('http://llm.invalid:11434', None, 'test-model', 2.0, 'ollama')
    client = LlmClient(settings, httpx.MockTransport(fail))
    answer = metrology_expert.answer_question('ограничение давления', client)
    assert answer.model == 'поиск по МИ без LLM'
    assert answer.sources and answer.sources[0]['excerpt']
