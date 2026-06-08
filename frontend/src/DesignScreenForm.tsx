import type { CalculationContext, CalculationTemplateCode, LineParameters, MeasurementMethod } from './api';

type Props = {
  projectName: string;
  selectedMethod: MeasurementMethod | null;
  line: LineParameters;
  context: CalculationContext;
  selectedTemplate: CalculationTemplateCode;
  totalStatus: string;
  deltaTotal: number;
  limit: number;
};

export function DesignScreenForm({ projectName, selectedMethod, line, context, selectedTemplate, totalStatus, deltaTotal, limit }: Props) {
  return (
    <section className="screen-form-card">
      <div className="screen-form-titlebar">
        <div>
          <div className="screen-form-kicker">Экранная форма / УУГ-01</div>
          <h2>Расчёт метрологических характеристик измерительной линии</h2>
        </div>
        <div className={`screen-form-status ${totalStatus === 'Не соответствует' ? 'danger' : totalStatus === 'Соответствует' ? 'ok' : 'warn'}`}>
          {totalStatus}
        </div>
      </div>

      <div className="screen-form-grid">
        <InfoCell label="Объект / расчёт" value={projectName || 'Без названия'} wide />
        <InfoCell label="Методика" value={selectedMethod?.registration_number ?? 'МИ не выбрана'} />
        <InfoCell label="Шаблон" value={selectedTemplate} />
        <InfoCell label="Q диапазон" value={`${line.q_min}–${line.q_max} ${line.q_unit}`} />
        <InfoCell label="P диапазон" value={`${line.p_min_mpa}–${line.p_max_mpa} МПа`} />
        <InfoCell label="T диапазон" value={`${line.t_min_c}…${line.t_max_c} °C`} />
        <InfoCell label="Рабочая точка" value={`Q=${context.working_flow_rate ?? '—'} · P=${context.gauge_pressure_mpa ?? '—'} · T=${context.temperature_c ?? '—'}`} wide />
        <InfoCell label="Итог / предел" value={`${deltaTotal.toFixed(3)}% / ${limit.toFixed(1)}%`} />
      </div>
    </section>
  );
}

function InfoCell({ label, value, wide = false }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={`screen-form-cell ${wide ? 'wide' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
