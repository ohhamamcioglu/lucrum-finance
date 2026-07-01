import { motion } from 'motion/react';
import { Link } from 'react-router-dom';
import { Wallet, BarChart2, ShieldAlert, TrendingUp, Settings, Newspaper, ShieldCheck } from 'lucide-react';
import { ActiveTab, UserSettings } from '../types';
import { useT } from '../i18n';
import { useAuth } from '../AuthContext';

interface SidebarProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
  settings: UserSettings;
}

export default function Sidebar({ activeTab, setActiveTab, settings }: SidebarProps) {
  const t = useT(settings.language);
  const { isAdmin } = useAuth();

  const menuItems = [
    { id: 'portfolio', label: t.portfolio, icon: Wallet },
    { id: 'analytics', label: t.analytics, icon: BarChart2 },
    { id: 'risk', label: t.risk, icon: ShieldAlert },
    { id: 'markets', label: t.markets, icon: TrendingUp },
    { id: 'news', label: t.news, icon: Newspaper },
    { id: 'settings', label: t.settings, icon: Settings },
  ] as const;

  return (
    <aside
      id="sidebar-container"
      className="bg-[#F1EFE9] text-[#4A443F] w-64 h-screen fixed left-0 top-0 border-r border-[#E8E2D9] flex flex-col justify-between py-6 z-50 select-none"
    >
      <div className="flex flex-col">
        {/* Logo and branding */}
        <div className="px-6 mb-10 flex flex-col">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-8 h-8 bg-[#8C9A86] rounded-full flex items-center justify-center text-white font-serif text-base font-medium">L</div>
            <span className="font-serif font-bold text-xl tracking-tight text-[#2D2926] hover:opacity-90 cursor-pointer">
              LUCRUM
            </span>
          </div>
          <span className="text-[9px] tracking-[0.25em] text-[#9E958C] uppercase font-semibold">
            {t.institutionalGrade}
          </span>
        </div>

        {/* Navigation Menu */}
        <nav className="flex-1 px-3 space-y-1.5">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;

            return (
              <button
                key={item.id}
                id={`sidebar-tab-${item.id}`}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center gap-3.5 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 relative group overflow-hidden ${
                  isActive
                    ? 'text-[#8C9A86] bg-[#8C9A86]/10 font-bold'
                    : 'text-[#6B645E] hover:bg-[#E8E2D9] hover:text-[#2D2926]'
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="sidebarActiveIndicator"
                    className="absolute right-0 top-0 bottom-0 w-1.5 bg-[#8C9A86] rounded-l-md"
                    transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  />
                )}
                <Icon className={`w-4 h-4 transition-colors ${isActive ? 'text-[#8C9A86]' : 'text-[#9E958C] group-hover:text-[#2D2926]'}`} />
                <span className="relative z-10">{item.label}</span>
              </button>
            );
          })}

          {isAdmin && (
            <Link
              to="/admin"
              id="sidebar-tab-admin"
              className="w-full flex items-center gap-3.5 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 text-[#6B645E] hover:bg-[#E8E2D9] hover:text-[#2D2926]"
            >
              <ShieldCheck className="w-4 h-4 text-[#9E958C]" />
              <span>{t.navAdmin}</span>
            </Link>
          )}
        </nav>
      </div>

      {/* User Profile Footer */}
      <div className="px-5 py-4 flex items-center gap-3.5 border-t border-[#E8E2D9] mt-auto bg-[#E8E2D9]/30">
        <img
          id="user-avatar-sidebar"
          className="w-9 h-9 rounded-full object-cover border border-[#D1CABF] bg-[#F1EFE9] shadow-sm"
          referrerPolicy="no-referrer"
          src={settings.userAvatar}
          alt={settings.userName}
        />
        <div className="overflow-hidden flex flex-col justify-center">
          <span className="text-[#2D2926] text-xs font-semibold truncate block leading-tight">
            {settings.userName}
          </span>
          <span className="text-[10px] text-[#9E958C] uppercase tracking-wider block mt-0.5 font-semibold">
            {settings.userRole}
          </span>
        </div>
      </div>
    </aside>
  );
}
