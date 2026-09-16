// usePersonaForm: Manages only persona form state.
// Do NOT add synthesis or knowledge asset state here.
import { useState } from "react";
import { toast } from "sonner";
import { fetchWithAuth } from "@/lib/apiClient";

export function usePersonaForm(personas: any[], mutatePersonas: any, mutateObjections: any) {
  const [isPersonaModalOpen, setIsPersonaModalOpen] = useState(false);
  const [editingPersonaId, setEditingPersonaId] = useState<string | null>(null);
  const [personaForm, setPersonaForm] = useState({
    title: "",
    target_titles: "",
    pain_points: "",
    value_prop: "",
    tone_tweaks: ""
  });

  const openPersonaModal = (persona?: any) => {
    if (persona) {
      setEditingPersonaId(persona.id);
      setPersonaForm({
        title: persona.title || persona.name || "",
        target_titles: Array.isArray(persona.target_titles) ? persona.target_titles.join(", ") : (persona.target_titles || ""),
        pain_points: Array.isArray(persona.pain_points) ? persona.pain_points.join("\n") : (persona.pain_points || ""),
        value_prop: persona.value_prop || "",
        tone_tweaks: persona.tone_tweaks || ""
      });
    } else {
      setEditingPersonaId(null);
      setPersonaForm({ title: "", target_titles: "", pain_points: "", value_prop: "", tone_tweaks: "" });
    }
    setIsPersonaModalOpen(true);
  };

  const handleSavePersona = async () => {
    if (!personaForm.title.trim()) {
      toast.error("Persona title is required");
      return;
    }
    
    const payload = {
      title: personaForm.title,
      target_titles: personaForm.target_titles.split(",").map((t: string) => t.trim()).filter(Boolean),
      painPoints: personaForm.pain_points.split("\n").map((t: string) => t.trim()).filter(Boolean),
      value_prop: personaForm.value_prop,
      tone_tweaks: personaForm.tone_tweaks
    };

    try {
      const url = editingPersonaId ? `/api/knowledge/personas/${editingPersonaId}` : "/api/knowledge/personas";
      const method = editingPersonaId ? "PUT" : "POST";
      
      const res = await fetchWithAuth(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      
      if (res.ok) {
        toast.success(editingPersonaId ? "Persona updated!" : "Persona created!");
        setIsPersonaModalOpen(false);
        mutatePersonas();
      } else {
        toast.error("Failed to save persona");
      }
    } catch (e) {
      toast.error("Error saving persona");
    }
  };

  const handleAddPersona = async () => {
    const tempPersona = { 
      id: 'temp-' + Date.now(), 
      name: "New Target Persona", 
      pain_points: "Missing pipeline\nLow reply rates", 
      value_prop: "", 
      tone_tweaks: "",
      created_at: new Date().toISOString() 
    };
    mutatePersonas((current: any[]) => [...(current || []), tempPersona], false);

    try {
      const res = await fetchWithAuth("/api/knowledge/personas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "New Target Persona", painPoints: ["Missing pipeline", "Low reply rates"] })
      });
      if (res.ok) {
        toast.success("Persona created!");
        mutatePersonas(); mutateObjections();
      } else {
        mutatePersonas();
        toast.error("Failed to create persona");
      }
    } catch (e) {
      mutatePersonas();
      toast.error("Error creating persona");
    }
  };

  const handleDeletePersona = async (id: string) => {
    try {
      const res = await fetchWithAuth(`/api/knowledge/personas/${id}`, { method: "DELETE" });
      if (res.ok) {
        toast.success("Persona deleted!");
        mutatePersonas(); mutateObjections();
      }
    } catch (e) {
      toast.error("Error deleting persona");
    }
  };

  return {
    isPersonaModalOpen, setIsPersonaModalOpen,
    editingPersonaId,
    personaForm, setPersonaForm,
    openPersonaModal,
    handleSavePersona,
    handleAddPersona,
    handleDeletePersona
  };
}
