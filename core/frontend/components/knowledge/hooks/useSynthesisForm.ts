// useSynthesisForm: Manages only synthesis form edit state.
// Do NOT add persona or asset state here.
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { fetchWithAuth } from "@/lib/apiClient";

export function useSynthesisForm(synthesis: any, mutateSynthesis: () => void) {
  const [isEditingSynthesis, setIsEditingSynthesis] = useState(false);
  const [editedValueProp, setEditedValueProp] = useState("");
  const [editedTone, setEditedTone] = useState("");
  const [editedTargetCustomer, setEditedTargetCustomer] = useState("");
  const [editedDifferentiators, setEditedDifferentiators] = useState("");
  const [editedProofPoints, setEditedProofPoints] = useState("");
  const [editedPainPoints, setEditedPainPoints] = useState("");
  const [editedBannedPhrases, setEditedBannedPhrases] = useState("");
  const [editedObjectionPlaybook, setEditedObjectionPlaybook] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (synthesis) {
      setEditedValueProp(synthesis.core_value_prop || "");
      setEditedTone(Array.isArray(synthesis.identified_tone) ? synthesis.identified_tone.join(", ") : (synthesis.identified_tone || ""));
      setEditedTargetCustomer(synthesis.target_customer_profile || "");
      setEditedDifferentiators(Array.isArray(synthesis.key_differentiators) ? synthesis.key_differentiators.join("\n") : (synthesis.key_differentiators || ""));
      setEditedProofPoints(Array.isArray(synthesis.proof_points) ? synthesis.proof_points.join("\n") : (synthesis.proof_points || ""));
      setEditedPainPoints(Array.isArray(synthesis.primary_pain_points_solved) ? synthesis.primary_pain_points_solved.join("\n") : (synthesis.primary_pain_points_solved || ""));
      setEditedBannedPhrases(Array.isArray(synthesis.banned_phrases) ? synthesis.banned_phrases.join("\n") : (synthesis.banned_phrases || ""));
      setEditedObjectionPlaybook(synthesis.objection_playbook || "");
    }
  }, [synthesis]);

  const handleSaveSynthesis = async () => {
    setIsSaving(true);
    try {
      const res = await fetchWithAuth("/api/assets/knowledge/synthesis", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          core_value_prop: editedValueProp, 
          identified_tone: editedTone.split(",").map(t => t.trim()).filter(Boolean),
          target_customer_profile: editedTargetCustomer,
          key_differentiators: editedDifferentiators.split("\n").map(t => t.trim()).filter(Boolean),
          proof_points: editedProofPoints.split("\n").map(t => t.trim()).filter(Boolean),
          primary_pain_points_solved: editedPainPoints.split("\n").map(t => t.trim()).filter(Boolean),
          banned_phrases: editedBannedPhrases,
          objection_playbook: editedObjectionPlaybook
        })
      });
      if (!res.ok) throw new Error("Failed to update synthesis");
      toast.success("AI Synthesis & Guidelines successfully updated.");
      setIsEditingSynthesis(false);
      mutateSynthesis();
    } catch (err) {
      toast.error("Failed to save changes.");
    } finally {
      setIsSaving(false);
    }
  };

  return {
    isEditingSynthesis, setIsEditingSynthesis,
    editedValueProp, setEditedValueProp,
    editedTone, setEditedTone,
    editedTargetCustomer, setEditedTargetCustomer,
    editedDifferentiators, setEditedDifferentiators,
    editedProofPoints, setEditedProofPoints,
    editedPainPoints, setEditedPainPoints,
    editedBannedPhrases, setEditedBannedPhrases,
    editedObjectionPlaybook, setEditedObjectionPlaybook,
    handleSaveSynthesis,
    isSaving
  };
}
