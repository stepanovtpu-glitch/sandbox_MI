import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Search, X } from 'lucide-react';
import type { MeasurementMethod } from './api';

const MEDIUM_TITLES: Record<string, string> = { png: 'ПНГ', pg: 'ПГ', sog: 'СОГ' };
const FLOWMETER_TITLES: Record<string, string> = {
  vortex: 'вихревой',
  ultrasonic: 'ультразвуковой',
  turbine: 'турбинный',
  rotary: 'ротационный',
  orifice: 'сужающее устройство',
};
const BASIS_SHORT: Record<string, string> = { working: 'раб. у.', standard: 'ст. у.' };

function formatNumber(value: number) {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
}

/** Строка сводки: по ней видно применимость МИ без открытия карточки. */
export function methodSummary(method: MeasurementMethod): string {
  const parts = [
    MEDIUM_TITLES[method.medium ?? ''] ?? null,
    `Q ${formatNumber(method.q_min)}–${formatNumber(method.q_max)} м³/ч${method.q_basis ? ` ${BASIS_SHORT[method.q_basis]}` : ''}`,
    `P ${method.p_min_mpa}–${method.p_max_mpa} МПа`,
    `T ${method.t_min_c}…${method.t_max_c} °C`,
    `δΣ ±${method.delta_total_max}%`,
    method.flowmeter_type ? (FLOWMETER_TITLES[method.flowmeter_type] ?? method.flowmeter_type) : null,
  ];
  return parts.filter(Boolean).join(' · ');
}

/**
 * Выбор методики измерений.
 *
 * Обычный список выпадающего меню показывал только регистрационный номер —
 * по нему нельзя понять, для какой среды и какого диапазона методика.
 * Поэтому выбор вынесен в окно: поиск по номеру и наименованию, а в строке
 * сразу видны среда, диапазоны, показатель точности и тип расходомера.
 */
export function MethodPicker({
  methods,
  selectedId,
  onSelect,
  label = 'Методика измерений',
}: {
  methods: MeasurementMethod[];
  selectedId: string;
  onSelect: (miId: string) => void;
  label?: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement | null>(null);
  const selected = methods.find((method) => method.mi_id === selectedId) ?? null;

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('keydown', onKey);
    inputRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen]);

  const found = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return methods;
    return methods.filter((method) =>
      `${method.registration_number} ${method.title} ${method.flowmeter_type ?? ''} ${methodSummary(method)}`
        .toLowerCase()
        .includes(normalized),
    );
  }, [methods, query]);

  return (
    <div className="method-picker">
      <span className="method-picker-label">{label}</span>
      <button className="method-picker-trigger" onClick={() => setIsOpen(true)} title="Выбрать методику измерений">
        <span className="method-picker-number">{selected?.registration_number ?? 'МИ не выбрана'}</span>
        {selected && <small>{selected.title}</small>}
        {selected && <small className="method-picker-summary">{methodSummary(selected)}</small>}
        <ChevronDown size={15} />
      </button>

      {isOpen && (
        <div className="method-picker-backdrop" onClick={() => setIsOpen(false)}>
          <div className="method-picker-dialog" onClick={(event) => event.stopPropagation()} role="dialog" aria-label="Выбор методики измерений">
            <div className="method-picker-head">
              <div>
                <span>Библиотека методик</span>
                <strong>Выбор МИ · найдено {found.length} из {methods.length}</strong>
              </div>
              <button className="ghost-button" onClick={() => setIsOpen(false)} title="Закрыть"><X size={15} /></button>
            </div>
            <label className="method-search">
              <Search size={14} />
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Номер, наименование, тип расходомера, среда"
              />
            </label>
            <div className="method-picker-list">
              {found.map((method) => (
                <button
                  className={`method-picker-row ${method.mi_id === selectedId ? 'active' : ''}`}
                  key={method.mi_id}
                  onClick={() => {
                    onSelect(method.mi_id);
                    setIsOpen(false);
                  }}
                >
                  <b>{method.registration_number}</b>
                  <span>{method.title}</span>
                  <small>{methodSummary(method)}</small>
                </button>
              ))}
              {found.length === 0 && <div className="empty-row">По запросу ничего не найдено</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
