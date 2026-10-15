import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { OrgProvider } from './context/OrgContext'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter basename="/admin">
      <OrgProvider>
        <App />
      </OrgProvider>
    </BrowserRouter>
  </React.StrictMode>
)