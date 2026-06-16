import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { TechnologyRecommendationPanel } from './TechnologyRecommendationPanel';
import './styles.css';
import './document.css';
import './history.css';
import './integrity.css';
import './system-status.css';
import './screen-form.css';
import './history-screen.css';
import './audit-panel.css';
import './technology-recommendation.css';
import './ui-polish.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
    <div className="technology-floating-panel">
      <TechnologyRecommendationPanel />
    </div>
  </React.StrictMode>,
);
