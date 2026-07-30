import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './tokens.css'   // design tokens + self-hosted fonts (must load before index.css)
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
