import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initLang } from './strings.ts'

// `await` antes de montar, no dentro de un efecto: con el idioma resuelto en un
// efecto, el primer render sale en el idioma equivocado y todo componente que lea
// `t()` en un valor inicial de `useState` se queda con esa cadena para siempre.
// Mount on every path (initLang never rejects, but guard against silent failures anyway).
initLang().finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
