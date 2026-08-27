import React from 'react';
import { motion } from 'framer-motion';
import { Upload, MessageCircleHeart, ShieldCheck, Stethoscope, Zap, Users, Clock, Award, ArrowRight } from 'lucide-react';

const steps = [
  { icon: Upload, title: 'Upload your report', description: 'Use the + button in Voice Assistant to add a PDF report or bill securely.' },
  { icon: MessageCircleHeart, title: 'Ask by voice or text', description: 'Ask what a result, medicine, charge, or instruction means in the way that feels easiest.' },
  { icon: ShieldCheck, title: 'Get clear, sourced answers', description: 'MedClear searches only your uploaded document and identifies the supporting page.' },
];

const features = [
  { icon: Zap, title: 'Lightning Fast', description: 'Get instant answers powered by AI' },
  { icon: Users, title: 'Patient Centric', description: 'Designed specifically for you' },
  { icon: Clock, title: '24/7 Available', description: 'Always here when you need help' },
  { icon: Award, title: 'Verified Accurate', description: 'Based on your actual documents' },
];

export default function HomePage({ openVoiceAssistant }) {
  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0, transition: { duration: 0.4 } },
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] w-full bg-gradient-hero px-4 py-6 md:px-8">
      <motion.div
        className="max-w-7xl mx-auto space-y-12 pb-8"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        {/* Hero Section */}
        <motion.section
          variants={itemVariants}
          className="relative overflow-hidden glass-lg p-8 md:p-12 lg:p-16 rounded-3xl"
        >
          {/* Background gradient */}
          <div className="absolute inset-0 bg-gradient-to-r from-purple-500/20 via-pink-500/20 to-purple-500/10 pointer-events-none" />

          <div className="relative space-y-6">
            <div className="flex items-center gap-2">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-r from-purple-500 to-pink-500 flex items-center justify-center animate-float">
                <Stethoscope size={24} className="text-white" />
              </div>
              <span className="text-sm font-semibold text-purple-300 uppercase tracking-wider">Your Health, Simplified</span>
            </div>

            <div className="space-y-4">
              <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-white leading-tight">
                Understand Your Medical Documents
              </h1>
              <p className="text-lg md:text-xl text-white/70 max-w-2xl">
                MedClear lets you upload a document and ask questions using your voice or keyboard. Answers are based on your own document, not general guesses.
              </p>
            </div>

            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={openVoiceAssistant}
              className="btn btn-primary flex items-center gap-2 text-lg"
            >
              Open Voice Assistant
              <ArrowRight size={20} />
            </motion.button>
          </div>
        </motion.section>

        {/* Features Grid */}
        <motion.section variants={itemVariants} className="space-y-6">
          <div>
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-2">Why Choose MedClear?</h2>
            <p className="text-white/60">Everything you need to understand your health documents</p>
          </div>

          <motion.div
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
            variants={containerVariants}
            initial="hidden"
            animate="show"
          >
            {features.map((feature) => {
              const Icon = feature.icon;
              return (
                <motion.div
                  key={feature.title}
                  variants={itemVariants}
                  className="card-hover"
                >
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-r from-purple-500/20 to-pink-500/20 flex items-center justify-center mb-4">
                    <Icon size={24} className="text-purple-400" />
                  </div>
                  <h3 className="text-lg font-semibold text-white mb-2">{feature.title}</h3>
                  <p className="text-white/60 text-sm">{feature.description}</p>
                </motion.div>
              );
            })}
          </motion.div>
        </motion.section>

        {/* How It Works */}
        <motion.section variants={itemVariants} className="space-y-6">
          <div>
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-2">How It Works</h2>
            <p className="text-white/60">Three simple steps to get started</p>
          </div>

          <motion.div
            className="grid grid-cols-1 md:grid-cols-3 gap-4"
            variants={containerVariants}
            initial="hidden"
            animate="show"
          >
            {steps.map(({ icon: Icon, title, description }, index) => (
              <motion.div
                key={title}
                variants={itemVariants}
                className="relative group"
              >
                <div className="absolute -inset-0.5 bg-gradient-to-r from-purple-500 to-pink-500 rounded-3xl blur opacity-0 group-hover:opacity-20 transition duration-1000" />
                <div className="card h-full relative">
                  <div className="flex items-start justify-between mb-4">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-r from-purple-500 to-pink-500 flex items-center justify-center flex-shrink-0">
                      <Icon size={24} className="text-white" />
                    </div>
                    <div className="text-3xl font-bold text-white/20">0{index + 1}</div>
                  </div>
                  <h3 className="text-xl font-semibold text-white mb-2">{title}</h3>
                  <p className="text-white/60 leading-relaxed">{description}</p>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </motion.section>

        {/* CTA Section */}
        <motion.section
          variants={itemVariants}
          className="glass-lg p-8 md:p-12 rounded-3xl text-center space-y-6"
        >
          <h2 className="text-3xl md:text-4xl font-bold text-white">Ready to Get Started?</h2>
          <p className="text-white/60 text-lg max-w-2xl mx-auto">
            Upload your health document and start asking questions. Our AI assistant is ready to help you understand everything.
          </p>
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={openVoiceAssistant}
            className="btn btn-primary mx-auto"
          >
            Open Voice Assistant
          </motion.button>
        </motion.section>
      </motion.div>
    </div>
  );
}
