import React from 'react';
import { Music, BookOpen, MessageSquare, Sliders } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';

export const Sidebar: React.FC = () => {
  const { activeTab, setActiveTab } = useAppStore();

  const TABS = [
    { id: "analysis", icon: <Music className="w-5 h-5" />, label: "Analysis" },
    { id: "theory", icon: <BookOpen className="w-5 h-5" />, label: "Theory" },
    { id: "chat", icon: <MessageSquare className="w-5 h-5" />, label: "Chat" },
    { id: "settings", icon: <Sliders className="w-5 h-5" />, label: "Settings" }
  ] as const;

  return (
    <div className="w-64 border-r border-gray-800 bg-black flex flex-col shrink-0">
      <div className="flex-1 py-6 px-4 space-y-2">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
              activeTab === tab.id 
                ? "bg-violet-600/20 text-violet-400 border border-violet-500/30" 
                : "text-gray-400 hover:bg-gray-900 hover:text-white border border-transparent"
            }`}
          >
            {tab.icon}
            <span className="font-medium">{tab.label}</span>
          </button>
        ))}
      </div>
      
      {/* Mini state visualization could go here */}
      <div className="p-4 border-t border-gray-800">
        <div className="text-xs text-gray-500 font-medium px-2 mb-2 uppercase tracking-wider">
          System Status
        </div>
        <div className="bg-gray-900 rounded-lg p-3 border border-gray-800 flex items-center space-x-3">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
          <span className="text-sm text-gray-300">All Systems Normal</span>
        </div>
      </div>
    </div>
  );
};
