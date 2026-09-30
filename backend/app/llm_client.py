"""Клиент корпоративной LLM.

Единая точка подключения языковой модели предприятия. Протокол — chat
completions, совместимый с OpenAI: так работают почти все корпоративные
шлюзы (vLLM, LiteLLM, Ollama, GigaChat-прокси), поэтому конкретная модель
задаётся конфигурацией, а не кодом.

Границы применения задал владелец продукта и они закреплены здесь, а не в
промптах:

- распознавание сканов МИ и извлечение полей — без ИИ, только
  детерминированные правила (см. method_ocr.py, scripts/ocr_mi_library.py);
- метрологические расчёты и вердикты подбора — только код (uug_selection,
  gas_physics, calculation_templates);
- LLM объясняет, формулирует и ищет: пересказ обоснования подбора языком
  технолога, черновик замечания метролога, ответы по тексту методики.
  Числа, диапазоны и вердикты она получает готовыми и не имеет права менять.

Пока переменные окружения не заданы, клиент отключён и все вызовы честно
возвращают статус «не настроено» — интерфейс не должен притворяться, что
модель есть.

Настройка (docker-compose / .env):
    GASMETER_LLM_BASE_URL   например https://llm.corp.local/v1
    GASMETER_LLM_API_KEY    ключ доступа (если шлюз его требует)
    GASMETER_LLM_MODEL      имя модели на шлюзе
    GASMETER_LLM_TIMEOUT    секунды, по умолчанию 60
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 60.0
MAX_TOKENS = 1200

# Запрещённые темы для модели — она не источник метрологических данных
SYSTEM_GUARDRAILS = (
    'Ты помощник в корпоративной программе учёта газа ООО «Иркутская нефтяная компания». '
    'Отвечай по-русски, кратко и по делу, техническим, но понятным языком. '
    'Все числа, диапазоны, регистрационные номера методик и вердикты берутся ТОЛЬКО из '
    'переданных тебе данных: не выдумывай значения, не пересчитывай величины и не изменяй '
    'выводы программы. Если данных не хватает, скажи об этом прямо.'
)


@dataclass(frozen=True)
class LlmSettings:
    base_url: str | None
    api_key: str | None
    model: str | None
    timeout_s: float

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    @classmethod
    def from_env(cls) -> 'LlmSettings':
        timeout_raw = os.environ.get('GASMETER_LLM_TIMEOUT', '').strip()
        try:
            timeout = float(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT_S
        except ValueError:
            timeout = DEFAULT_TIMEOUT_S
        return cls(
            base_url=(os.environ.get('GASMETER_LLM_BASE_URL') or '').strip().rstrip('/') or None,
            api_key=(os.environ.get('GASMETER_LLM_API_KEY') or '').strip() or None,
            model=(os.environ.get('GASMETER_LLM_MODEL') or '').strip() or None,
            timeout_s=timeout,
        )


@dataclass
class LlmReply:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class LlmStatus:
    configured: bool
    reachable: bool | None
    base_url: str | None
    model: str | None
    detail: str
    usage_policy: list[str] = field(default_factory=lambda: [
        'Распознавание сканов МИ — без ИИ, только детерминированные правила.',
        'Расчёты и вердикты подбора — только код; модель их не меняет.',
        'Модель объясняет, формулирует и ищет по переданным ей данным.',
    ])


class LlmNotConfigured(RuntimeError):
    """Модель не подключена: переменные окружения не заданы."""


class LlmClient:
    def __init__(self, settings: LlmSettings | None = None, transport: httpx.BaseTransport | None = None):
        self.settings = settings or LlmSettings.from_env()
        # transport подменяется в тестах — сеть в автотестах не нужна
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        if self.settings.api_key:
            headers['Authorization'] = f'Bearer {self.settings.api_key}'
        return headers

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.settings.timeout_s, transport=self._transport)

    def status(self, probe: bool = True) -> LlmStatus:
        if not self.settings.configured:
            return LlmStatus(
                configured=False, reachable=None, base_url=self.settings.base_url, model=self.settings.model,
                detail='Корпоративная LLM не подключена: задайте GASMETER_LLM_BASE_URL и GASMETER_LLM_MODEL.',
            )
        if not probe:
            return LlmStatus(True, None, self.settings.base_url, self.settings.model, 'Настроена; доступность не проверялась.')
        try:
            with self._client() as client:
                response = client.get(f'{self.settings.base_url}/models', headers=self._headers())
            reachable = response.status_code < 500
            detail = 'Шлюз отвечает.' if response.status_code < 400 else f'Шлюз ответил кодом {response.status_code}.'
        except httpx.HTTPError as error:
            reachable = False
            detail = f'Шлюз недоступен: {error.__class__.__name__}.'
        return LlmStatus(True, reachable, self.settings.base_url, self.settings.model, detail)

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = MAX_TOKENS) -> LlmReply:
        """Один запрос к модели. Системная инструкция с ограничениями добавляется всегда."""
        if not self.settings.configured:
            raise LlmNotConfigured('Корпоративная LLM не настроена.')
        payload = {
            'model': self.settings.model,
            'messages': [{'role': 'system', 'content': SYSTEM_GUARDRAILS}, *messages],
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        with self._client() as client:
            response = client.post(f'{self.settings.base_url}/chat/completions', json=payload, headers=self._headers())
        response.raise_for_status()
        body = response.json()
        try:
            text = body['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError('Неожиданный формат ответа LLM-шлюза') from error
        usage = body.get('usage') or {}
        return LlmReply(
            text=(text or '').strip(),
            model=str(body.get('model') or self.settings.model),
            prompt_tokens=usage.get('prompt_tokens'),
            completion_tokens=usage.get('completion_tokens'),
        )


def explain_selection(client: LlmClient, selection: dict, audience: str = 'technologist') -> LlmReply:
    """Пересказать результат подбора МИ языком адресата.

    Модели передаётся уже готовый результат select_uug: вердикт, причины,
    предупреждения, рекомендации. Её задача — связный текст для служебной
    записки, а не новое решение.
    """
    role_title = {
        'technologist': 'технолога: что означает вердикт для режима узла и что предпринять',
        'kip': 'службы КИПиА: какие приборы и почему, что заказать',
        'metrologist': 'метролога: соответствие области применения МИ и допускам',
    }.get(audience, 'специалиста')
    best = selection.get('best_method') or {}
    facts = {
        'вердикт': best.get('verdict_title'),
        'методика': best.get('registration_number'),
        'наименование': best.get('title'),
        'обоснование': best.get('reasons') or [],
        'оговорки': best.get('caveats') or [],
        'рекомендации технологу': selection.get('technologist_advice') or [],
        'предупреждения по алгоритмам': selection.get('algorithm_warnings') or [],
        'диапазоны': [
            f"{item.get('label')}: {item.get('q_min')}–{item.get('q_max')} {item.get('unit')}"
            for item in (selection.get('ranges') or [])
        ],
        'сводка': selection.get('summary'),
    }
    lines = [f'{key}: {value}' for key, value in facts.items() if value]
    prompt = (
        f'Составь короткое (до 120 слов) пояснение для {role_title}. '
        'Используй только приведённые факты, ничего не добавляй и не пересчитывай.\n\n'
        + '\n'.join(lines)
    )
    return client.chat([{'role': 'user', 'content': prompt}])
