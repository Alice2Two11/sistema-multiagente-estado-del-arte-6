from __future__ import annotations
import json

PROMPT_VERSION = "v17_thematic_agent_no_structure_01"


def build_thematic_prompt(
    context, valid_sources, title_map, repair_plan=None,
):
    # NOTA (removido): 04 ya no propone `suggested_state_of_art_structure`.
    # Esa propuesta preliminar de esquema era un subproducto de este mismo
    # prompt, pero solo la consumía 05 como una pista opcional (nunca
    # vinculante) -- ver context_builder.py de outline_generation, de donde
    # ya se quitó. El esquema real que usa el redactor (06) lo genera 05,
    # con más contexto (perfil de generación, tabla comparativa, KB
    # completa) y su propio min_sections/max_sections. Por eso ya no se le
    # pide estructura a este agente ni se le pasan min_sections/max_sections/
    # enforce_section_count -- 04 se limita a temas, vacíos y dimensiones
    # comparativas, que es su responsabilidad real.
    repair = ""
    if repair_plan:
        repair = "\nREPARACIÓN DIRIGIDA:\n" + json.dumps(
            repair_plan,
            ensure_ascii=False,
        )
    return (
        "Analiza exclusivamente la KB proporcionada. No uses Ground Truth, "
        "bibliografía ni conocimiento externo.\n"
        "Devuelve un objeto JSON con corpus_summary, themes, research_gaps "
        "y comparative_dimensions.\n"
        "Cada tema debe tener representative_papers con source_filename y title exactos. "
        "Cada gap y dimensión debe tener fuentes válidas.\n"
        "El campo del nombre de cada tema se llama EXACTAMENTE \"theme_name\" -- nunca "
        "\"theme_title\" ni \"title\" (\"title\" es para representative_papers).\n"
        "En research_gaps, el texto del vacío va en el campo \"description\" -- nunca "
        "\"gap_description\". En comparative_dimensions, el nombre de la dimensión va en "
        "el campo \"dimension\" -- nunca \"dimension_name\".\n"
        f"FUENTES VÁLIDAS: {json.dumps(valid_sources, ensure_ascii=False)}\n"
        f"TÍTULOS: {json.dumps(title_map, ensure_ascii=False)}\n"
        f"CORPUS: {json.dumps(context, ensure_ascii=False)}{repair}"
    )
