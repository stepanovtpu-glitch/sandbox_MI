import { useEffect } from 'react';

type ApplyRecommendationDetail = {
  mi_id: string;
  calculation_template: string;
  q_min: number;
  q_max: number;
  p_working_mpa: number;
  t_working_c: number;
};

const nativeInputSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
const nativeSelectSetter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')?.set;

function setInputByLabel(labelText: string, value: number) {
  const labels = Array.from(document.querySelectorAll('label.field'));
  const label = labels.find((item) => item.querySelector('span')?.textContent?.trim() === labelText);
  const input = label?.querySelector('input');
  if (!input || !nativeInputSetter) return;
  nativeInputSetter.call(input, String(value));
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

function setSelectByLabel(labelText: string, value: string) {
  const labels = Array.from(document.querySelectorAll('label.field'));
  const label = labels.find((item) => item.querySelector('span')?.textContent?.trim() === labelText);
  const select = label?.querySelector('select');
  if (!select || !nativeSelectSetter) return;
  nativeSelectSetter.call(select, value);
  select.dispatchEvent(new Event('change', { bubbles: true }));
}

function setProjectName(detail: ApplyRecommendationDetail) {
  const labels = Array.from(document.querySelectorAll('label.field'));
  const label = labels.find((item) => item.querySelector('span')?.textContent?.trim() === 'Название расчёта');
  const input = label?.querySelector('input');
  if (!input || !nativeInputSetter) return;
  nativeInputSetter.call(input, `Технологический подбор МИ: ${detail.mi_id}`);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

function applyRecommendation(detail: ApplyRecommendationDetail) {
  setSelectByLabel('Методика', detail.mi_id);
  setSelectByLabel('Шаблон расчёта', detail.calculation_template);

  setInputByLabel('Q min, м³/ч', detail.q_min);
  setInputByLabel('Q max, м³/ч', detail.q_max);
  setInputByLabel('P min, МПа', detail.p_working_mpa);
  setInputByLabel('P max, МПа', detail.p_working_mpa);
  setInputByLabel('T min, °C', detail.t_working_c);
  setInputByLabel('T max, °C', detail.t_working_c);

  setInputByLabel('Q рабочий, м³/ч', detail.q_min);
  setInputByLabel('P избыточное, МПа', detail.p_working_mpa);
  setInputByLabel('Температура, °C', detail.t_working_c);
  setProjectName(detail);
}

export function ApplyRecommendationBridge() {
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<ApplyRecommendationDetail>).detail;
      if (!detail) return;
      setTimeout(() => applyRecommendation(detail), 0);
    };
    window.addEventListener('gasmeter:apply-technology-recommendation', handler);
    return () => window.removeEventListener('gasmeter:apply-technology-recommendation', handler);
  }, []);

  return null;
}
