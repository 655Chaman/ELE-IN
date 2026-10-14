-- Migration 096: Register Credit Action Costs for Specialized AI Features (M-05 Hardening)
-- Registers standard credit costs for Competitive Displacement, Social Pre-Warm, and Multimodal Studio:
-- 1. displacement_pitch: 2 credits (Tailored competitive buyout pitch generation)
-- 2. social_prewarm_comment: 1 credit (Contextual feed comment synthesis)
-- 3. thought_leadership_post: 2 credits (Long-form thought leadership post)
-- 4. multimodal_voice_script: 2 credits (Conversational voice note script)
-- 5. multimodal_video_card: 3 credits (Video prospecting card & thumbnail copy)

INSERT INTO public.credit_action_costs (action_type, credits, category, description) VALUES
('displacement_pitch', 2, 'displacement', 'AI Competitor Displacement Pitch Generation'),
('social_prewarm_comment', 1, 'social', 'AI Contextual Social Pre-Warm Comment'),
('thought_leadership_post', 2, 'social', 'AI Thought Leadership Post Generation'),
('multimodal_voice_script', 2, 'multimodal', 'AI Conversational Voice Drop Script'),
('multimodal_video_card', 3, 'multimodal', 'AI Video Prospecting Card Generation')
ON CONFLICT (action_type) DO UPDATE SET 
    credits = EXCLUDED.credits,
    category = EXCLUDED.category,
    description = EXCLUDED.description;
