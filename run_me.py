
import React, { useState, useEffect } from 'react';
import { Match } from './types';
import MatchCard from './components/MatchCard';
import { calculateProbs } from './services/mathUtils';
import { Search, Filter, RefreshCw, Trophy, CalendarDays } from 'lucide-react';

const App: React.FC = () => {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('All');

  useEffect(() => {
    // 獲取今天 00:00:00 和 23:59:59 的時間戳 (Local Time)
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
    const endOfToday = startOfToday + 86400;

    const mockMatches: Match[] = [
      {
        id: 1,
        league: 'Premier League',
        timestamp: startOfToday + 3600 * 20, // 今晚 8 點
        home: { id: 33, name: 'Manchester United', logo: 'https://picsum.photos/id/10/48/48', rank: 6, form: 'WWDLW' },
        away: { id: 34, name: 'Newcastle United', logo: 'https://picsum.photos/id/11/48/48', rank: 8, form: 'LDWWW' },
        status: 'NS',
        score: { home: null, away: null },
        odds: { home: 1.85, draw: 3.5, away: 4.2 }
      },
      {
        id: 2,
        league: 'La Liga',
        timestamp: startOfToday + 3600 * 22, // 今晚 10 點
        home: { id: 541, name: 'Real Madrid', logo: 'https://picsum.photos/id/12/48/48', rank: 1, form: 'WWWWW' },
        away: { id: 542, name: 'Barcelona', logo: 'https://picsum.photos/id/13/48/48', rank: 2, form: 'WWDWW' },
        status: 'NS',
        score: { home: null, away: null },
        odds: { home: 2.1, draw: 3.4, away: 3.6 }
      },
      {
        id: 3,
        league: 'Bundesliga',
        timestamp: startOfToday - 3600 * 24, // 昨天
        home: { id: 157, name: 'Bayern Munich', logo: 'https://picsum.photos/id/14/48/48', rank: 2, form: 'WLWWW' },
        away: { id: 165, name: 'Borussia Dortmund', logo: 'https://picsum.photos/id/15/48/48', rank: 4, form: 'WWLWW' },
        status: 'FT',
        score: { home: 1, away: 1 },
        odds: { home: 1.5, draw: 4.8, away: 6.5 }
      },
      {
        id: 4,
        league: 'Serie A',
        timestamp: startOfToday + 3600 * 48, // 後天
        home: { id: 489, name: 'Inter Milan', logo: 'https://picsum.photos/id/16/48/48', rank: 1, form: 'WWWWW' },
        away: { id: 492, name: 'Napoli', logo: 'https://picsum.photos/id/17/48/48', rank: 7, form: 'LDDWL' },
        status: 'NS',
        score: { home: null, away: null },
        odds: { home: 1.6, draw: 3.9, away: 5.8 }
      }
    ];

    // 核心邏輯：僅處理今日賽事 (Quota Optimization Test)
    const todayOnlyMatches = mockMatches.filter(m => m.timestamp >= startOfToday && m.timestamp < endOfToday);

    const processed = todayOnlyMatches.map(m => {
      const hXG = (20 - (m.home.rank || 10)) / 5 + Math.random();
      const aXG = (20 - (m.away.rank || 10)) / 6 + Math.random();
      const probs = calculateProbs(hXG, aXG);

      let valueBet: 'home' | 'away' | null = null;
      if (m.odds) {
        if ((probs.homeWinProb / 100) > (1 / m.odds.home) * 1.05) valueBet = 'home';
        else if ((probs.awayWinProb / 100) > (1 / m.odds.away) * 1.05) valueBet = 'away';
      }

      return {
        ...m,
        predictions: {
          xGHome: hXG,
          xGAway: aXG,
          ...probs
        },
        valueBet
      };
    });

    setTimeout(() => {
      setMatches(processed);
      setLoading(false);
    }, 800);
  }, []);

  const leagues = ['All', 'Premier League', 'La Liga', 'Bundesliga', 'Serie A'];
  const filteredMatches = filter === 'All' 
    ? matches 
    : matches.filter(m => m.league === filter);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-10">
        <div>
          <h1 className="text-4xl font-black bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent flex items-center gap-3">
            <Trophy className="text-blue-500" size={36} />
            Football xG Hub
          </h1>
          <div className="flex items-center gap-2 mt-2">
            <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-500 text-[10px] font-bold uppercase tracking-wider">
              <CalendarDays size={12} />
              Testing Mode: Today Only
            </span>
            <p className="text-slate-400 text-sm">已優化以節省 API 請求次數</p>
          </div>
        </div>
        
        <div className="flex items-center gap-3 bg-slate-800 p-1 rounded-xl border border-slate-700">
          {leagues.map(l => (
            <button 
              key={l}
              onClick={() => setFilter(l)}
              className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${filter === l ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20' : 'text-slate-400 hover:text-white'}`}
            >
              {l}
            </button>
          ))}
        </div>
      </header>

      {/* Main Stats Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        <div className="bg-slate-800 border border-slate-700 p-6 rounded-2xl">
          <div className="text-slate-500 text-xs font-bold uppercase mb-1">今日賽事數</div>
          <div className="text-3xl font-black text-white">{matches.length}</div>
        </div>
        <div className="bg-slate-800 border border-slate-700 p-6 rounded-2xl border-l-4 border-l-green-500">
          <div className="text-slate-500 text-xs font-bold uppercase mb-1">價值投注 (Value)</div>
          <div className="text-3xl font-black text-green-400">{matches.filter(m => m.valueBet).length}</div>
        </div>
        <div className="bg-slate-800 border border-slate-700 p-6 rounded-2xl border-l-4 border-l-blue-500">
          <div className="text-slate-500 text-xs font-bold uppercase mb-1">分析深度</div>
          <div className="text-3xl font-black text-blue-400">Normal</div>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-20">
          <RefreshCw className="text-blue-500 animate-spin mb-4" size={48} />
          <p className="text-slate-400 font-medium">正在計算今日賽事 xG 數據...</p>
        </div>
      ) : (
        <>
          {filteredMatches.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredMatches.map(match => (
                <MatchCard key={match.id} match={match} />
              ))}
            </div>
          ) : (
            <div className="text-center py-20 bg-slate-800/50 rounded-3xl border border-dashed border-slate-700">
              <p className="text-slate-500">今日暫無符合條件的聯賽賽事</p>
            </div>
          )}
        </>
      )}

      {/* Footer */}
      <footer className="mt-20 pt-8 border-t border-slate-800 text-center text-slate-500 text-sm">
        <p>© 2025 Football xG Hub. 測試模式僅加載今日數據。</p>
      </footer>
    </div>
  );
};

export default App;
