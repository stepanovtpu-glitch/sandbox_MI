import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles.css';
import './document.css';
import './history.css';
import './integrity.css';
import './system-status.css';
import './screen-form.css';
import './history-screen.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
