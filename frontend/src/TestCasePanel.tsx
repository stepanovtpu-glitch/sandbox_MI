import { useState } from 'react';
import { addMethodTestCase, runMethodTestCases, type MeasurementMethod, type MeasurementMethodVersion, type MethodTestResult } from './api';

type Props = {
  selectedMethod: MeasurementMethod;
  version?: MeasurementMethodVersion;
  onVersionUpdated: (version: MeasurementMethodVersion) => void;
};

const defaultInputData = JSON.stringify({
  line: {
    pipe_dn_mm: 100,
    flowmeter_dn_mm: 100,
    straight_before_dn: 10,
    straight_after_dn: 5,
    q_min: 40,
    q_max: 1600,
    q_unit: 'm3/h',
    p_min_mpa: 0.12,
    p_max_mpa: 2.5,
    t_min_c: -50,
    t_max_c: 50
  },
  errors: {
    delta_q: 1.5,
    delta_p: 0.5,
    delta_t: 0.34,
    delta_vc: 0.05,
    delta_c: 0.33,
    kp: 1,
    kt: 1,
    kc: 1
  }
}, null, 2);

export function TestCasePanel({ selectedMethod, version, onVersionUpdated }: Props) {
  const [name, setName] = useState('Эталонный пример из приложения МИ');
  const [expectedDelta, setExpectedDelta] = useState(3.1);
  const [tolerance, setTolerance] = useState(0.01);
  const [inputData, setInputData] = useState(defaultInputData);
  const [results, setResults] = useState<MethodTestResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  if (!version) return <div className="document-empty">Нет активной версии для контрольных примеров</div>;

  const handleAddTestCase = async () => {
    setError(null);
    try {
      const parsedInput = JSON.parse(inputData);
      parsedInput.method = selectedMethod;
      const updated = await addMethodTestCase(selectedMethod.mi_id, version.version_id, {
        name,
        input_data: parsedInput,
        expected_result: { delta_total: expectedDelta },
        tolerance,
      });
      onVersionUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка добавления контрольного примера');
    }
  };

  const handleRunTests = async () => {
    setIsRunning(true);
    setError(null);
    try {
      setResults(await runMethodTestCases(selectedMethod.mi_id, version.version_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка запуска проверки');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="library-card">
      <div className="library-card-title">Контрольные примеры МИ</div>
      <TextField label="Название примера" value={name} onChange={setName} />
      <div className="library-form-grid">
        <NumberField label="Ожидаемая U/δΣ, %" value={expectedDelta} onChange={setExpectedDelta} />
        <NumberField label="Допуск" value={tolerance} onChange={setTolerance} />
      </div>
      <label className="field">
        <span>Входные данные JSON</span>
        <textarea value={inputData} onChange={(event) => setInputData(event.target.value)} />
      </label>
      <div className="library-actions">
        <button className="ghost-button" onClick={handleAddTestCase}>Добавить пример</button>
        <button className="primary-button" onClick={handleRunTests} disabled={isRunning || version.test_cases.length === 0}>
          {isRunning ? 'Проверка...' : 'Запустить проверку'}
        </button>
      </div>
      <div className="testcase-list">
        {version.test_cases.map((testCase) => (
          <div className="testcase-row" key={testCase.name}>
            <strong>{testCase.name}</strong>
            <span>ожидание: {String(testCase.expected_result.delta_total)} · допуск: {testCase.tolerance}</span>
          </div>
        ))}
      </div>
      {results.length > 0 && (
        <div className="testcase-list">
          {results.map((result) => (
            <div className={`testcase-row ${result.status}`} key={result.name}>
              <strong>{result.status === 'pass' ? '✓' : result.status === 'fail' ? '✗' : '!' } {result.name}</strong>
              <span>{result.message}</span>
            </div>
          ))}
        </div>
      )}
      {error && <div className="api-error">{error}</div>}
    </div>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="field"><span>{label}</span><input value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return <label className="field"><span>{label}</span><input type="number" step="any" value={value} onChange={(event) => onChange(Number(event.target.value))} /></label>;
}
