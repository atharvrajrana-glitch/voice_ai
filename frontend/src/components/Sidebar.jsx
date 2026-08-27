import React from 'react';
import { motion } from 'framer-motion';
import { LayoutDashboard, MessageSquare, FileText, Settings, HelpCircle, ChevronRight } from 'lucide-react';

const menuItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, color: 'from-purple-500 to-pink-500' },
  { id: 'voice', label: 'Voice Assistant', icon: MessageSquare, color: 'from-blue-500 to-cyan-500' },
  { id: 'documents', label: 'Documents', icon: FileText, color: 'from-orange-500 to-red-500' },
];

const secondaryItems = [
  { id: 'settings', label: 'Settings', icon: Settings },
  { id: 'help', label: 'Help & Support', icon: HelpCircle },
];

export default function Sidebar({ activePage, onPageChange, isOpen, onClose }) {
  const containerVariants = {
    hidden: { opacity: 0, x: -50 },
    show: {
      opacity: 1,
      x: 0,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, x: -20 },
    show: { opacity: 1, x: 0, transition: { duration: 0.3 } },
  };

  return (
    <>
      {/* Mobile Overlay */}
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 lg:hidden"
        />
      )}

      {/* Sidebar */}
      <motion.aside
        initial={{ x: -100 }}
        animate={{ x: 0 }}
        className={`fixed left-0 top-16 h-[calc(100vh-4rem)] w-64 glass border-r border-white/10 p-6 overflow-y-auto z-40 lg:static lg:translate-x-0 transition-transform duration-300 ${
          isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <motion.nav
          className="space-y-8"
          variants={containerVariants}
          initial="hidden"
          animate="show"
        >
          {/* Main Menu */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-white/30 uppercase tracking-wider px-3">Menu</p>
            <div className="space-y-1">
              {menuItems.map((item) => {
                const Icon = item.icon;
                const isActive = activePage === item.id;

                return (
                  <motion.button
                    key={item.id}
                    variants={itemVariants}
                    onClick={() => {
                      onPageChange(item.id);
                      onClose?.();
                    }}
                    className={`w-full flex items-center justify-between px-4 py-3 rounded-lg transition-all duration-300 group ${
                      isActive
                        ? 'bg-white/10 border border-white/20 text-white'
                        : 'text-white/60 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`p-2 rounded-lg ${
                          isActive
                            ? `bg-gradient-to-r ${item.color}`
                            : 'bg-white/10 group-hover:bg-white/20'
                        }`}
                      >
                        <Icon size={18} className={isActive ? 'text-white' : ''} />
                      </div>
                      <span className="font-medium">{item.label}</span>
                    </div>
                    {isActive && <ChevronRight size={18} />}
                  </motion.button>
                );
              })}
            </div>
          </div>

          {/* Secondary Menu */}
          <div className="space-y-2 border-t border-white/10 pt-8">
            <p className="text-xs font-semibold text-white/30 uppercase tracking-wider px-3">Support</p>
            <div className="space-y-1">
              {secondaryItems.map((item) => {
                const Icon = item.icon;

                return (
                  <motion.button
                    key={item.id}
                    variants={itemVariants}
                    onClick={() => onPageChange(item.id)}
                    className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-white/60 hover:text-white hover:bg-white/5 transition-all duration-300"
                  >
                    <Icon size={18} />
                    <span className="font-medium">{item.label}</span>
                  </motion.button>
                );
              })}
            </div>
          </div>

          {/* Status Info */}
          <div className="glass-sm p-4 space-y-2">
            <div className="flex items-center gap-2">
              <div className="status-dot-active" />
              <p className="text-sm font-medium text-white">System Online</p>
            </div>
            <p className="text-xs text-white/40">All services running normally</p>
          </div>
        </motion.nav>
      </motion.aside>
    </>
  );
}
