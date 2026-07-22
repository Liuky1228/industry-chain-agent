import { BrowserRouter, Routes, Route } from 'react-router-dom'
import HomePage from './components/HomePage'
import ResultPage from './components/ResultPage'

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="app-header">
          <div className="header-content">
            <h1 className="logo" onClick={() => window.location.href = '/'}>
              <span className="logo-icon">&#128279;</span>
              产业链分析 Agent
            </h1>
            <span className="header-subtitle">AI 驱动的产业链智能分析平台</span>
          </div>
        </header>

        <main className="app-main">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/task/:taskId" element={<ResultPage />} />
          </Routes>
        </main>

        <footer className="app-footer">
          <p>Powered by DeepSeek AI | 数据来源：东方财富、巨潮资讯</p>
        </footer>
      </div>
    </BrowserRouter>
  )
}

export default App
