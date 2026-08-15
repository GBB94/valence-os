import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './tokens.css'   // design tokens + self-hosted fonts (must load before index.css)
import './skins.css'    // optional skin token overrides — after tokens.css so a skin wins the cascade
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
