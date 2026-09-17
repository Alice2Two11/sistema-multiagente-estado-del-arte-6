# Sistema Multiagente para Generación y Verificación de Estados del Arte

Sistema multiagente basado en modelos de lenguaje grandes para generar,
verificar y evaluar estados del arte científicos a partir de un corpus
cerrado de artículos proporcionado por el usuario. La arquitectura combina
recuperación aumentada por generación (RAG), extracción estructurada de
conocimiento, análisis temático, generación de esquema, redacción basada
en evidencia y verificación factual a nivel de afirmación, con una matriz
de trazabilidad que vincula cada afirmación con la evidencia recuperada,
los documentos fuente y el veredicto de verificación correspondiente.

## 1. Visión general

El sistema se organiza en dos componentes que se ejecutan en orden, sobre
la misma carpeta de proyecto (`PROJECT_DIR`):

1. **Preparación del corpus** (`codigo_fuente.zip`, notebooks de Colab):
   configuración del experimento, ingesta documental y construcción de la
   base vectorial. Se ejecuta de forma interactiva, una vez por
   experimento.
2. **Orquestador del pipeline** (`src/`, este repositorio): extracción de
   conocimiento, análisis temático, generación de esquema, redacción,
   verificación y evaluación. Se ejecuta como script, coordinado por
   LangGraph, con estado transaccional persistido en disco.

Ambos componentes comparten una única fuente de verdad para la
configuración del experimento: `active_experiment.json`, escrito por el
primer componente y leído por el segundo.

## 2. El paquete de notebooks (`codigo_fuente.zip`)

Este paquete, distribuido por separado, contiene los notebooks operativos
que se ejecutan en Colab **antes** de invocar el orquestador:

| Notebook | Responsabilidad |
|---|---|
| `00_setup_config.ipynb` | Define el experimento activo: tema, corpus, perfil de generación (idioma, extensión, modo de escritura, estilo de citación), política de recuperación (`RAG_POLICY`, con sus perfiles y umbral mínimo de relevancia) y credenciales de sesión. Escribe `active_experiment.json` y los módulos de configuración que consumen los notebooks siguientes (`config.py`, `rag_policy.py`, `generation_config.py`, entre otros). |
| `01_ingesta_memoria_documental.ipynb` | Procesa los PDF del corpus: extracción y normalización de texto, detección de secciones, segmentación en fragmentos (1200 caracteres, solapamiento de 350), exclusión de bibliografía y de secciones de revisión de literatura (siguiendo los patrones definidos en `rag_policy.py`), y aislamiento explícito del Ground Truth (nunca se incorpora a la memoria documental ni a la base vectorial). |
| `02_rag_chroma_retriever.ipynb` | Construye la colección persistente de ChromaDB a partir de los fragmentos válidos, usando el modelo de embeddings configurado (`all-MiniLM-L6-v2` por defecto). Expone también el retriever de referencia con diversidad por fuente y umbral mínimo de relevancia, usado como base de las funciones de recuperación equivalentes dentro de `src/`. |
| `Corrida_03_a_08.ipynb` | Invoca el orquestador (`src/orchestration_langgraph/pipeline_graph.py`) como subproceso, con la ruta de `PROJECT_DIR` ya preparada por los tres notebooks anteriores, gestiona la posible ejecución separada de la etapa de evaluación cuando la verificación se detiene con salida parcial disponible, y expone un interruptor (`FRESH_START`) para pasar `--fresh-start` al orquestador sin editar el comando. |

Los notebooks 00-02 son responsables de todo lo que el orquestador **da
por sentado** al arrancar: que `active_experiment.json` existe y es
válido, que la base vectorial de Chroma está indexada y su manifiesto
coincide con el experimento activo, y que la credencial de OpenAI está
disponible para la sesión. El orquestador no reconstruye ninguno de estos
prerrequisitos — si falta alguno, falla explícitamente indicando qué
notebook ejecutar.

## 3. El orquestador (`src/`)

### 3.1. Etapas del pipeline

```
03_agente_extraccion_kb          -- extracción de fichas científicas por paper
03B_extraccion_cuantitativa_kb   -- normalización y verificación de datos numéricos
04_agente_analisis_tematico      -- agrupación temática, comparaciones, vacíos de investigación
05_generador_esquema             -- estructura jerárquica del estado del arte
06_agente_redactor               -- redacción de secciones basada en evidencia
07_agente_verificador            -- verificación factual a nivel de afirmación
08_evaluacion_experimental       -- métricas automáticas, factuales y discursivas
```

La coordinación se implementa con LangGraph: cada etapa es un nodo, y las
transiciones (`ADVANCE`, `RETRY`, `RETURN`, `HALT_STAGE`, `STOP_PIPELINE`)
se determinan de forma condicional a partir de la calidad real del
resultado de cada etapa, no de un recorrido fijo. En particular, un
`RETURN` de 07 hacia 06 reincorpora el flujo al ciclo de escritura y
verificación (sección 3.3) hasta que 07 apruebe o agote sus rondas
disponibles.

### 3.2. Estructura del repositorio

```
src/
├── agents/                  Lógica de cada etapa (contrato AgentInput -> AgentResult)
├── adapters/                Construcción de runtimes reales (LLM, Chroma) por etapa
├── capabilities/            Implementación de etapas sin clase Agent dedicada (03B)
├── config/                  Políticas por defecto y validación fail-closed por etapa
├── contracts/                AgentInput, AgentResult y tipos compartidos del protocolo
├── orchestration/           Motor de decisión, registro de etapas, StageSpec
├── orchestration_langgraph/ Grafo de ejecución, nodos, enrutamiento condicional
├── runtime/                 Protocolo transaccional (PREPARE/EXECUTE/COMMIT) por etapa
├── state/                   StateStore, PipelineState, fingerprints
└── tools/                   Lógica de dominio de cada etapa (extracción, redacción,
                              verificación, evaluación), organizada por etapa
```

### 3.3. El ciclo de escritura y verificación (06 ↔ 07)

Cuando 07 identifica una afirmación que requiere modificación y existe
evidencia suficiente para sustentar el cambio, emite una solicitud de
revisión dirigida a 06. El orquestador gestiona el retorno a la etapa de
redacción, donde se modifica únicamente el contenido señalado, preservando
la identidad de las afirmaciones no afectadas. La versión revisada vuelve
a 07 para una nueva verificación. El ciclo tiene un número máximo de
rondas configurable (por defecto 3); al alcanzarlo, o cuando 07 aprueba,
el pipeline continúa hacia 08.

Cada ronda del ciclo se persiste de forma transaccional en
`{experiment_dir}/05_outputs/writer_verifier_cycle/round_NN/`: 07 crea la
ronda en `AWAITING_REVISION`, 06 la completa (nunca la crea) a
`REVISION_COMPLETED`, y un segundo intento de completar la misma ronda se
rechaza explícitamente.

### 3.4. Recuperación adaptativa de evidencia

Durante la verificación, la evidencia se recupera de forma independiente
del contexto usado en la redacción, restringida a los documentos
autorizados para cada afirmación. Cuando la evidencia inicial resulta
insuficiente, el sistema puede reformular la consulta o ajustar la
cantidad de resultados recuperados antes de emitir un veredicto, dentro de
un presupuesto de recuperaciones adicionales por afirmación (por defecto
1). Todas las estrategias de recuperación —la del perfil general de RAG,
la de extracción y la de verificación— aplican un piso mínimo de
relevancia semántica: un fragmento solo se considera evidencia si su
similitud con la consulta supera ese umbral, evitando que se complete un
cupo de resultados con contenido sin relación real.

### 3.5. Identidad estable de afirmaciones (`claim_uid`)

Cada afirmación conserva un identificador estable a través de las
sucesivas rondas de redacción y verificación, junto con su historial de
versiones y relaciones de procedencia cuando el contenido es modificado.
Esto permite seguir una misma afirmación durante todo el ciclo sin perder
su vínculo con la evidencia documental utilizada en cada punto.

### 3.6. Estado transaccional y reproducibilidad

Cada etapa se ejecuta bajo el mismo protocolo (`src/state/state_store.py`,
`run_stage()` en `src/orchestration/stage_execution.py`):

1. **PREPARE**: se registra la intención de ejecutar la etapa con un
   `decision_id` nuevo.
2. **EXECUTE**: se invoca la lógica real de la etapa (agente o
   capability), produciendo un `AgentResult`.
3. **COMMIT**: el resultado se persiste junto con sus fingerprints de
   entrada; solo entonces se considera parte del estado oficial del
   pipeline.
4. **RESUME**: al reiniciar el pipeline, cada etapa evalúa si su último
   commit sigue vigente (comparando fingerprints) antes de decidir si
   reejecutar o reutilizar el resultado existente (`SKIPPED_FRESH`).

`active_experiment.json` es la única fuente de verdad para toda
configuración que el orquestador consume; ningún módulo de `src/`
mantiene una copia propia de valores que deban coincidir con ella —
cuando una etapa necesita una política más elaborada que la almacenada
directamente en `active_experiment.json` (por ejemplo, la política de RAG
con sus patrones de exclusión), la deriva en tiempo real a partir del
mismo archivo generado por el notebook 00, en vez de mantener una copia
local.

## 4. Cómo ejecutar

### 4.1. Preparación (una vez por experimento)

Ejecutar en Colab, en orden, los notebooks del paquete `codigo_fuente.zip`:
`00_setup_config.ipynb` → `01_ingesta_memoria_documental.ipynb` →
`02_rag_chroma_retriever.ipynb`.

### 4.2. Ejecución del pipeline

La vía operativa real es el notebook `Corrida_03_a_08.ipynb` (parte del
paquete de notebooks, sección 2): arma el comando hacia
`src.orchestration_langgraph.pipeline_graph` con la ruta de `PROJECT_DIR`
ya resuelta, y gestiona la posible invocación separada de la etapa 08
cuando 07 se detiene con salida parcial disponible para evaluación —
consultando primero si existe un resultado de 07 utilizable, y dejando
que el propio orquestador decida si 08 debe ejecutarse de nuevo o
reconocerse como vigente (`SKIPPED_FRESH`).

Ese notebook, a su vez, invoca directamente:

```bash
python3 -m src.orchestration_langgraph.pipeline_graph \
  --project-dir /ruta/a/PROJECT_DIR \
  --until 08_evaluacion_experimental
```

`run_pipeline_via_langgraph()` interpreta la transición real que devuelve
cada etapa — el mismo comando cubre automáticamente el ciclo `06 ↔ 07`
sin ningún flag especial.

### 4.3. Flags disponibles

| Flag | Efecto |
|---|---|
| `--until <etapa>` | Detiene el pipeline apenas esa etapa produce un resultado. |
| `--start-stage <etapa>` | Arranca directamente en la etapa indicada, en vez de la primera de `CANONICAL_STAGE_ORDER`. Vía oficial para reintentar una sola etapa desde un estado terminal (`FAILED`/`HALT_STAGE`). |
| `--force-rerun` | Reejecuta la etapa inicial aunque ya esté `COMPLETED` y vigente según fingerprints. Las etapas posteriores siguen evaluando las suyas normalmente. |
| `--fresh-start` | Reinicia `attempts_used` de todas las etapas a 0, el ciclo `writer_verifier` a `NOT_STARTED`, limpia cualquier ejecución pendiente y archiva (nunca borra) rondas del ciclo ya persistidas. Implica `--force-rerun`. |

Además del flag explícito, el pipeline compara automáticamente un hash del
árbol `src/` contra el de la corrida anterior (`PROJECT_DIR/.last_code_hash.txt`)
y aplica un `--fresh-start` implícito si detecta cambios, sin necesidad de
pedirlo — de forma que una actualización del código nunca reutilice en
silencio un resultado calculado con la versión anterior.

## 5. Configuración del experimento

`active_experiment.json` (escrito por `00_setup_config.ipynb`) centraliza:

- Identidad del experimento (`experiment_id`, `run_id`) y rutas base.
- `openai_model`, modelo de embeddings, colección y directorio de Chroma.
- `generation_profile`: tema, idioma, extensión objetivo (palabras mínimas
  y máximas, número de secciones), modo de escritura, foco y estilo de
  citación.
- `rag_policy`: aislamiento del Ground Truth, exclusión de secciones de
  revisión y bibliografía, perfiles de recuperación (`top_k`, `fetch_k`,
  máximo de fragmentos por fuente, umbral mínimo de relevancia).
- Políticas por etapa (`max_attempts`, temperaturas, umbrales de cobertura
  y validación), con valores por defecto en `src/config/` que se combinan
  con lo declarado en `active_experiment.json`; los campos sin un valor
  explícito por parte del notebook 00 no tienen un valor implícito —la
  ejecución falla pidiendo completarlos, en vez de asumir uno.

## 6. Outputs principales

### Etapa 06 (borrador)

- `state_of_art_draft.json` — secciones, citas y afirmaciones.
- `draft_generation_manifest.json`, `draft_validation_report.json`,
  `draft_length_check.csv`, `draft_quality_check.csv`.

### Etapa 07 (verificación)

En `PROJECT_DIR/{experiment_id}/05_outputs/06_verification_traceability/`:

- `agent07_runtime_report.json` — métricas de ejecución, incluida la
  actividad de recuperación adaptativa por afirmación.
- `provisional_verification_traceability_bundle.json` — matriz de
  trazabilidad completa (afirmación, evidencia, veredicto, correcciones y
  reverificaciones cuando aplican).
- `draft_validation_report.json` (referencia al de 06, para verificar
  consistencia entre lo que 06 produjo y lo que 07 evaluó).

### Etapa 08 (evaluación)

En `08_final_results/`:

- `estado_del_arte_generado.md` / `.json` — documento final.
- `resumen_experimento.csv` — métricas agregadas (similitud, BERTScore,
  LLM Judge, factuales).
- `trazabilidad_claims_final.csv` — una fila por afirmación activa, con su
  veredicto, evidencia y razones.
- `metricas_evaluacion.csv`, `resumen_por_seccion.csv`,
  `tabla_comparativa_papers.csv`, `gaps_y_limitaciones.csv`.

## 7. Métricas de evaluación

| Categoría | Métricas |
|---|---|
| Similitud con la referencia humana | ROUGE-L, similitud semántica (embeddings), BERTScore |
| Calidad discursiva (LLM Judge) | Coherencia, organización, profundidad crítica, calidad de síntesis, claridad argumentativa |
| Factuales | Precisión factual, tasa de alucinación (estricta y amplia), tasa no verificada, cobertura de evidencia, cobertura de trazabilidad, error de citación, error numérico |

La precisión factual y la cobertura de evidencia miden aspectos distintos
de las métricas de similitud textual: una afirmación puede ser
semánticamente cercana a la referencia humana sin estar completamente
respaldada por la evidencia documental, y viceversa. Por diseño, la
cobertura de trazabilidad no implica corrección — indica que la
afirmación fue registrada y su procedencia es auditable,
independientemente de su veredicto.

## 8. Desenlace de una ejecución

Una ejecución que completa 08 puede resultar en:

- **Aprobado para publicación**: todas las condiciones de verificación
  fueron satisfechas.
- **`PARTIAL_HALT`**: la etapa de evaluación completó su trabajo sobre la
  salida disponible, pero al menos una condición de verificación no pudo
  resolverse automáticamente con la evidencia disponible
  (`AGENT07_NON_CORRECTABLE_ISSUE`) y queda marcada para revisión humana.
  La salida sigue siendo utilizable para evaluación experimental.

Este segundo desenlace es un resultado esperado del diseño, no una falla
del sistema: cuando la evidencia disponible no permite resolver una
afirmación con confianza suficiente, el sistema prefiere derivarla a
revisión humana antes que forzar un veredicto automático.

## 9. Consideraciones para nuevos dominios o corpus

- La densidad del corpus (número de artículos y su cobertura temática
  respecto al esquema generado) influye directamente en la proporción de
  afirmaciones con respaldo documental completo. Corpus más pequeños o
  temáticamente dispersos tienden a producir una proporción mayor de
  afirmaciones con evidencia parcial.
- El comportamiento del modelo de lenguaje durante la verificación no es
  completamente determinista incluso con temperatura configurada en cero;
  se recomienda más de una ejecución por corpus para caracterizar la
  variabilidad antes de sacar conclusiones de una sola corrida.
- Ampliar el corpus de un dominio, o revisar la asignación de artículos
  por sección en el esquema generado, son las palancas más directas para
  mejorar la cobertura de evidencia en un dominio específico.
