
import React, { useState, useEffect } from 'react';
import { Match } from './types';
import MatchCard from './components/MatchCard';
import { calculateProbs } from './services/mathUtils';
import { RefreshCw, Trophy, CalendarDays } from 'lucide-react';

const App: React.FC = () => {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('All');

  useEffect(() => {
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
    const endOfToday = startOfToday + 86400;

    const mockMatches: Match[] = [
      {
        id: 1,
        league: 'Premier League',
        timestamp: startOfToday + 3600 * 18, 
        home: { id: 33, name: 'Manchester United', logo: '', rank: 6, form: 'WWDLW', injuries: 3 },
        away: { id: 34, name: 'Newcastle', logo: '', rank: 8, form: 'LDWWW', injuries: 1 },
        status: 'NS',
        score: { home: null, away: null },
        h2h: { home: 4, draw: 3, away: 3 },
        odds: { home: 1.85, draw: 3.5, away: 4.2 }
      },
      {
        id: 2,
        league: 'La Liga',
        timestamp: startOfToday + 3600 * 20,
        home: { id: 541, name: 'Real Madrid', logo: '', rank: 1, form: 'WWWWW', injuries: 0 },
        away: { id: 542, name: 'Barcelona', logo: '', rank: 2, form: 'WWDWW', injuries: 2 },
        status: 'NS',
        score: { home: null, away: null },
        h2h: { home: 5, draw: 2, away: 3 },
        odds: { home: 2.1, draw: 3.4, away: 3.6 }
      }
    ];

    // Filter today and calculate
    const processed = mockMatches
      .filter(m => m.timestamp >= startOfToday && m.timestamp < endOfToday)
      .map(m => {
        // Special logic: combine rank and injuries into xG
        const hBase = (22 - (m.home.rank || 10)) / 10;
        const aBase = (22 - (m.away.rank || 10)) / 10;
        const hXG = hBase - (m.home.injuries || 0) * 0.1 + Math.random();
        const aXG = aBase - (m.away.injuries || 0) * 0.1 + Math.random();
        
        const probs = calculateProbs(hXG, aXG);

        let valueBet: 'home' | 'away' | null = null;
        if (m.odds) {
          if ((probs.homeWinProb / 100) > (1 / m.odds.home) * 1.08) valueBet = 'home';
          else if ((probs.awayWinProb / 100) > (1 / m.odds.away) * 1.08) valueBet = 'away';
        }

        return {
          ...m,
          predictions: { xGHome: hXG, xGAway: aXG, ...probs, source: 'Specialized Hybrid' },
          valueBet
        };
      });

    setTimeout(() => {
      setMatches(processed);
      setLoading(false);
    }, 1000);
  }, []);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-10">
        <div>
          <h1 className="text-4xl font-black bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent flex items-center gap-3">
            <Trophy className="text-cyan-500" size={36} />
            Football AI Pro
          </h1>
          <div className="flex items-center gap-2 mt-2">
            <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-500 text-[10px] font-bold uppercase tracking-wider">
              <CalendarDays size={12} />
              V38.1 Eco Mode: Today Only
            </span>
          </div>
        </div>
      </header>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20">
          <RefreshCw className="text-cyan-500 animate-spin mb-4" size={48} />
          <p className="text-slate-400 font-medium tracking-widest text-xs uppercase">Initializing Specialized Hybrid Model...</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {matches.map(match => <MatchCard key={match.id} match={match} />)}
          {matches.length === 0 && (
            <div className="col-span-full text-center py-20 bg-slate-800/50 rounded-3xl border border-dashed border-slate-700">
              <p className="text-slate-500">No matches found for today's snapshot.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default App;
