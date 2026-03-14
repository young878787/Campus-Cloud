import { useState, useEffect } from 'react'
import { MessageSquare, ImageIcon, Loader2, AlertCircle } from 'lucide-react'
import ChatBox from './components/ChatBox'

function App() {
  const [modelInfo, setModelInfo] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    // 獲取模型資訊
    fetch('/api/model-info')
      .then(res => res.json())
      .then(data => {
        setModelInfo(data)
        setLoading(false)
      })
      .catch(err => {
        setError('無法連接到 vLLM 服務')
        setLoading(false)
      })
  }, [])

  return (
    <div className="h-screen bg-white flex flex-col font-sans text-gray-900 overflow-hidden">
      {/* 頂部標題 */}
      <header className="shrink-0 flex items-center justify-between px-6 py-3 border-b border-gray-100 bg-white/80 backdrop-blur-md z-10 w-full">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-gray-900 rounded-lg flex items-center justify-center shadow-sm">
            <MessageSquare className="w-4 h-4 text-white" />
          </div>
          <h1 className="text-lg font-semibold tracking-tight">
            AI Assistant
          </h1>
        </div>
        
        <div className="flex items-center gap-3">
          {loading && (
            <div className="flex items-center gap-2 text-gray-500 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>正在連接...</span>
            </div>
          )}
          
          {error && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-red-50 border border-red-200 rounded-md text-red-600 shadow-sm text-sm">
              <AlertCircle className="w-4 h-4" />
              <span>{error}</span>
            </div>
          )}
          
          {modelInfo && (
            <div className="flex items-center gap-2 px-3 py-1 bg-gray-50 border border-gray-200 rounded-full text-gray-700 shadow-sm text-sm">
              <div className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </div>
              <span className="font-medium text-xs">
                {modelInfo.model_name.split('/').pop()}
              </span>
              {modelInfo.is_image_capable && (
                <div className="flex items-center gap-1 ml-1 border-l border-gray-200 pl-2">
                  <ImageIcon className="w-3.5 h-3.5 text-gray-400" />
                </div>
              )}
            </div>
          )}
        </div>
      </header>

      {/* 聊天容器 */}
      <div className="flex-1 w-full bg-white relative flex flex-col min-h-0">
        {!loading && !error && modelInfo && (
          <ChatBox modelInfo={modelInfo} />
        )}
      </div>
    </div>
  )
}

export default App
