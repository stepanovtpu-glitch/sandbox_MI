import { useState, type FormEvent } from 'react';
import { BookOpenText, LoaderCircle, Send } from 'lucide-react';
import { askMetrologyExpert, type MetrologyExpertReply } from './api';

export function MetrologyExpertScreen() {
  const [question, setQuestion] = useState('');
  const [reply, setReply] = useState<MetrologyExpertReply | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      setReply(await askMetrologyExpert(question.trim()));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось получить ответ.');
    } finally {
      setBusy(false);
    }
  }

  return <section className="workspace-screen metrology-expert-screen">
    <article className="panel metrology-expert-card">
      <div className="panel-header"><strong><BookOpenText size={18} /> Метрологический эксперт</strong></div>
      <p className="muted-copy">Задайте вопрос по методике измерений. При доступной корпоративной LLM получите ответ со ссылками на МИ; без неё откроются найденные фрагменты распознанных текстов для проверки по скану.</p>
      <form className="expert-question-form" onSubmit={submit}>
        <label className="field"><span>Вопрос</span><textarea value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={2000} rows={4} placeholder="Например: какие ограничения по температуре указаны в МИ для расходомера…" /></label>
        <div className="expert-form-footer"><span>{question.length}/2000 · Ответ справочный, расчёт и решение метролога не заменяет.</span><button className="primary-button" disabled={busy || !question.trim()}>{busy ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />} Спросить</button></div>
      </form>
      {error && <div className="api-error">{error}</div>}
      {reply && <div className="expert-answer"><div className="answer-heading">{reply.model === 'поиск по МИ без LLM' ? 'Найдено в библиотеке' : 'Ответ'} · {reply.model}</div><div className="answer-text">{reply.text}</div>{reply.sources.length > 0 && <div className="expert-sources"><strong>Источники</strong>{reply.sources.map((source) => source.excerpt ? <details key={source.reference}><summary>{source.review_state === 'confirmed' ? '✓' : '⚠'} {source.reference}</summary><div className="expert-source-excerpt">{source.excerpt}</div></details> : <span key={source.reference}>{source.review_state === 'confirmed' ? '✓' : '⚠'} {source.reference}</span>)}</div>}</div>}
    </article>
  </section>;
}
