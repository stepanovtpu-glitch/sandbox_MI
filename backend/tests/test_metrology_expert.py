import httpx
import json
from fastapi.testclient import TestClient

from app import metrology_expert
from app.llm_client import LlmClient, LlmSettings
from app.main import app


def test_source_search_remains_useful_without_model(monkeypatch, tmp_path):
    monkeypatch.setattr(metrology_expert, '_corpus_dir', lambda: tmp_path)
    monkeypatch.setattr(metrology_expert, '_database_ocr_sources', lambda: [])
    monkeypatch.delenv('GASMETER_LLM_BASE_URL', raising=False)
    monkeypatch.delenv('GASMETER_LLM_MODEL', raising=False)
    (tmp_path / 'scan.pdf.txt').write_text('Для расходомера указан рабочий диапазон давления от 0,1 до 5 МПа.', encoding='utf-8')
    (tmp_path / 'scan.pdf.json').write_text(json.dumps({'file_name': 'Методика.pdf'}, ensure_ascii=False), encoding='utf-8')
    raw = tmp_path / 'raw'; raw.mkdir()
    (raw / 'Методика.pdf').write_bytes(b'%PDF-1.4\nsource')
    monkeypatch.setattr(metrology_expert, '_library_raw_dir', lambda: raw)
    answer = metrology_expert.answer_question('диапазон давления расходомера')
    assert answer.model == 'поиск по МИ без LLM'
    assert answer.sources[0]['review_state'] == 'unverified'
    assert answer.sources[0]['scan_file_name'] == 'Методика.pdf'
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


def test_scan_endpoint_reads_only_library_pdf(monkeypatch, tmp_path):
    from app import database
    monkeypatch.setenv('GASMETER_REQUIRE_AUTH', '0')
    monkeypatch.setenv('GASMETER_MI_LIBRARY_DIR', str(tmp_path))
    monkeypatch.setenv('GASMETER_DATABASE_URL', '')
    monkeypatch.setattr(database, 'DB_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'api.db')
    raw = tmp_path / 'raw'; raw.mkdir()
    (raw / 'МИ.pdf').write_bytes(b'%PDF-1.4\nsource')
    client = TestClient(app)
    response = client.get('/api/mi-library/scans/МИ.pdf', headers={'X-Role': 'metrologist'})
    assert response.status_code == 200 and response.content.startswith(b'%PDF')
    assert client.get('/api/mi-library/scans/missing.pdf', headers={'X-Role': 'metrologist'}).status_code == 404
