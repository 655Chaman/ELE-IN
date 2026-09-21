import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, ChevronRight, Settings2, User, Heart, ThumbsUp, Eye, ArrowRight } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';

export function WarmupWizard({ onComplete, onCancel }: { onComplete: (nodes: any[]) => void, onCancel: () => void }) {
  const [step, setStep] = useState(1);
  const [config, setConfig] = useState({
    viewProfile: { enabled: true, delay: 0 },
    followProfile: { enabled: true, delay: 1 },
    likePost: { enabled: true, delay: 1, quantity: 2, reactionType: 'Like' },
    endorseSkill: { enabled: true, delay: 1, quantity: 1 }
  });

  const handleNext = () => setStep(s => Math.min(s + 1, 5));
  const handlePrev = () => setStep(s => Math.max(s - 1, 1));

  const generateSequence = () => {
    let currentNodes: any[] = [];
    
    // Build from bottom to top
    if (config.endorseSkill.enabled) {
      currentNodes = [{
        id: uuidv4(),
        type: 'endorse_skill',
        data: { 
          delay_days: config.endorseSkill.delay, 
          quantity: config.endorseSkill.quantity,
          fallback: "Endorse however many exist"
        },
        children: { "then": currentNodes }
      }];
    }
    
    if (config.likePost.enabled) {
      currentNodes = [{
        id: uuidv4(),
        type: 'like_post',
        data: { 
          delay_days: config.likePost.delay,
          quantity: config.likePost.quantity,
          reaction_type: config.likePost.reactionType
        },
        children: { "then": currentNodes }
      }];
    }
    
    if (config.followProfile.enabled) {
      currentNodes = [{
        id: uuidv4(),
        type: 'follow_profile',
        data: { delay_days: config.followProfile.delay },
        children: { "then": currentNodes }
      }];
    }
    
    if (config.viewProfile.enabled) {
      currentNodes = [{
        id: uuidv4(),
        type: 'view_profile',
        data: { delay_days: config.viewProfile.delay },
        children: { "then": currentNodes }
      }];
    }

    (window as any)._nodes = currentNodes;
    onComplete(currentNodes);
  };

  return (
    <div className="absolute inset-0 bg-background z-50 flex items-center justify-center p-8 overflow-y-auto">
      <div className="max-w-2xl w-full bg-card border border-border/50 rounded-3xl shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-border/50 bg-muted/10 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-foreground flex items-center gap-2">
              <span className="bg-primary/20 text-primary px-2 py-1 rounded-md text-xs tracking-wider uppercase">Wizard</span>
              Guided Warm-up Sequence
            </h2>
            <p className="text-sm text-muted-foreground mt-1">Configure a proven 4-step sequence to warm up your prospects before connecting.</p>
          </div>
          <button onClick={onCancel} className="text-muted-foreground hover:text-foreground">Cancel</button>
        </div>

        {/* Body */}
        <div className="flex-1 p-8">
          <AnimatePresence mode="wait">
            {step === 1 && (
              <motion.div key="step1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <div className="flex items-center gap-4 mb-6">
                  <div className="w-12 h-12 rounded-2xl bg-primary/20 text-primary flex items-center justify-center">
                    <Eye size={24} />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold">Step 1: View Profile</h3>
                    <p className="text-sm text-muted-foreground">Creates a 'viewed your profile' notification. Warmed leads have a 40-50% higher connection acceptance rate.</p>
                  </div>
                </div>
                
                <div className="space-y-6 bg-muted/5 p-6 rounded-2xl border border-border/50">
                  <label className="flex items-center justify-between cursor-pointer">
                    <span className="text-sm font-medium">Enable this step</span>
                    <input type="checkbox" checked={config.viewProfile.enabled} onChange={e => setConfig(c => ({...c, viewProfile: {...c.viewProfile, enabled: e.target.checked}}))} className="toggle" />
                  </label>
                  
                  {config.viewProfile.enabled && (
                    <div>
                      <label className="block text-sm font-medium mb-2">Delay before step (days)</label>
                      <input type="number" min="0" value={config.viewProfile.delay} onChange={e => setConfig(c => ({...c, viewProfile: {...c.viewProfile, delay: parseInt(e.target.value)||0}}))} className="w-full bg-background border border-border/50 rounded-lg px-3 py-2 text-sm" />
                      <p className="text-xs text-muted-foreground mt-2">Default is 0 (immediate execution).</p>
                    </div>
                  )}
                </div>
              </motion.div>
            )}

            {step === 2 && (
              <motion.div key="step2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <div className="flex items-center gap-4 mb-6">
                  <div className="w-12 h-12 rounded-2xl bg-primary/20 text-primary flex items-center justify-center">
                    <User size={24} />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold">Step 2: Follow Profile</h3>
                    <p className="text-sm text-muted-foreground">Follow their public profile to trigger a notification and make your posts visible to them.</p>
                  </div>
                </div>
                
                <div className="space-y-6 bg-muted/5 p-6 rounded-2xl border border-border/50">
                  <label className="flex items-center justify-between cursor-pointer">
                    <span className="text-sm font-medium">Enable this step</span>
                    <input type="checkbox" checked={config.followProfile.enabled} onChange={e => setConfig(c => ({...c, followProfile: {...c.followProfile, enabled: e.target.checked}}))} className="toggle" />
                  </label>
                  
                  {config.followProfile.enabled && (
                    <div>
                      <label className="block text-sm font-medium mb-2">Wait before following (days)</label>
                      <input type="number" min="0" value={config.followProfile.delay} onChange={e => setConfig(c => ({...c, followProfile: {...c.followProfile, delay: parseInt(e.target.value)||0}}))} className="w-full bg-background border border-border/50 rounded-lg px-3 py-2 text-sm" />
                      <p className="text-xs text-muted-foreground mt-2">Give it a day after viewing their profile so it looks organic.</p>
                    </div>
                  )}
                </div>
              </motion.div>
            )}

            {step === 3 && (
              <motion.div key="step3" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <div className="flex items-center gap-4 mb-6">
                  <div className="w-12 h-12 rounded-2xl bg-primary/20 text-primary flex items-center justify-center">
                    <Heart size={24} />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold">Step 3: React to Post</h3>
                    <p className="text-sm text-muted-foreground">Like their most recent post to establish immediate relevance.</p>
                  </div>
                </div>
                
                <div className="space-y-6 bg-muted/5 p-6 rounded-2xl border border-border/50">
                  <label className="flex items-center justify-between cursor-pointer">
                    <span className="text-sm font-medium">Enable this step</span>
                    <input type="checkbox" checked={config.likePost.enabled} onChange={e => setConfig(c => ({...c, likePost: {...c.likePost, enabled: e.target.checked}}))} className="toggle" />
                  </label>
                  
                  {config.likePost.enabled && (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium mb-2">Delay (days)</label>
                        <input type="number" min="0" value={config.likePost.delay} onChange={e => setConfig(c => ({...c, likePost: {...c.likePost, delay: parseInt(e.target.value)||0}}))} className="w-full bg-background border border-border/50 rounded-lg px-3 py-2 text-sm" />
                      </div>
                      <div>
                        <label className="block text-sm font-medium mb-2">Number of posts</label>
                        <input type="number" min="1" max="5" value={config.likePost.quantity} onChange={e => setConfig(c => ({...c, likePost: {...c.likePost, quantity: parseInt(e.target.value)||1}}))} className="w-full bg-background border border-border/50 rounded-lg px-3 py-2 text-sm" />
                      </div>
                      <div className="col-span-2">
                        <label className="block text-sm font-medium mb-2">Reaction Type</label>
                        <select value={config.likePost.reactionType} onChange={e => setConfig(c => ({...c, likePost: {...c.likePost, reactionType: e.target.value}}))} className="w-full bg-background border border-border/50 rounded-lg px-3 py-2 text-sm">
                          {["Like", "Insightful", "Celebrate", "Support", "Funny"].map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            )}

            {step === 4 && (
              <motion.div key="step4" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <div className="flex items-center gap-4 mb-6">
                  <div className="w-12 h-12 rounded-2xl bg-success/20 text-success flex items-center justify-center">
                    <ThumbsUp size={24} />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold">Step 4: Endorse Skill</h3>
                    <p className="text-sm text-muted-foreground">Endorse one of their top skills. A highly visible, rarely automated action.</p>
                  </div>
                </div>
                
                <div className="space-y-6 bg-muted/5 p-6 rounded-2xl border border-border/50">
                  <label className="flex items-center justify-between cursor-pointer">
                    <span className="text-sm font-medium">Enable this step</span>
                    <input type="checkbox" checked={config.endorseSkill.enabled} onChange={e => setConfig(c => ({...c, endorseSkill: {...c.endorseSkill, enabled: e.target.checked}}))} className="toggle" />
                  </label>
                  
                  {config.endorseSkill.enabled && (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium mb-2">Delay (days)</label>
                        <input type="number" min="0" value={config.endorseSkill.delay} onChange={e => setConfig(c => ({...c, endorseSkill: {...c.endorseSkill, delay: parseInt(e.target.value)||0}}))} className="w-full bg-background border border-border/50 rounded-lg px-3 py-2 text-sm" />
                      </div>
                      <div>
                        <label className="block text-sm font-medium mb-2">Number of skills</label>
                        <input type="number" min="1" max="5" value={config.endorseSkill.quantity} onChange={e => setConfig(c => ({...c, endorseSkill: {...c.endorseSkill, quantity: parseInt(e.target.value)||1}}))} className="w-full bg-background border border-border/50 rounded-lg px-3 py-2 text-sm" />
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            )}

            {step === 5 && (
              <motion.div key="step5" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <div className="text-center py-8">
                  <div className="w-16 h-16 rounded-full bg-success/20 text-success flex items-center justify-center mx-auto mb-6">
                    <Check size={32} />
                  </div>
                  <h3 className="text-2xl font-bold text-foreground mb-3">You're all set!</h3>
                  <p className="text-sm text-muted-foreground max-w-sm mx-auto mb-8">
                    Your sequence is ready. We will generate the flow based on your configuration. After generation, you can add a Connection Request or direct messages on top.
                  </p>
                  
                  <button onClick={generateSequence} className="px-8 py-3 bg-primary text-primary-foreground font-bold rounded-xl hover:bg-primary/90 transition-all flex items-center justify-center gap-2 mx-auto">
                    Generate Sequence <ArrowRight size={18} />
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Footer */}
        {step < 5 && (
          <div className="p-6 border-t border-border/50 bg-muted/10 flex items-center justify-between">
            <div className="flex gap-1">
              {[1,2,3,4].map(i => (
                <div key={i} className={`h-2 rounded-full transition-all ${i === step ? 'w-8 bg-primary' : i < step ? 'w-4 bg-primary/40' : 'w-4 bg-border'}`} />
              ))}
            </div>
            
            <div className="flex gap-3">
              <button disabled={step === 1} onClick={handlePrev} className="px-5 py-2 text-sm font-medium border border-border/50 rounded-lg bg-background hover:bg-muted/50 disabled:opacity-50">Back</button>
              <button onClick={handleNext} className="px-5 py-2 text-sm font-medium rounded-lg bg-foreground text-background hover:bg-foreground/90 flex items-center gap-1">
                Next <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
