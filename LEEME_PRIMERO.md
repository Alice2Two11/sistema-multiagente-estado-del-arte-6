# Léeme primero

Guía rápida de orientación para este repositorio. Para el detalle técnico
completo, ver `README.md`.

## ¿Qué es esto?

Un sistema multiagente que genera, verifica y evalúa estados del arte
científicos a partir de un corpus cerrado de artículos proporcionado por
el usuario, con trazabilidad completa entre cada afirmación generada, la
evidencia recuperada, el documento fuente y el veredicto de verificación.

## Dos partes, un mismo `PROJECT_DIR`

1. **`codigo_fuente.zip`** (notebooks de Colab, distribuido aparte):
   configura el experimento, procesa los PDF del corpus y construye la
   base vectorial. Se corre una vez por experimento, en orden:
   `00_setup_config` → `01_ingesta_memoria_documental` →
   `02_rag_chroma_retriever`.
2. **Este repositorio (`src/`)**: el orquestador del pipeline — extracción,
   análisis temático, esquema, redacción, verificación y evaluación. Se
   corre como script, después de que los 3 notebooks anteriores dejaron
   `active_experiment.json` y la base de Chroma listos.

Ver `README.md` secciones 1 y 2 para el detalle de cada componente.

## Estructura de `src/`

```
agents/                  Lógica de cada etapa
adapters/                Construcción de runtimes reales (LLM, Chroma)
capabilities/            Etapas sin clase Agent dedicada
config/                  Políticas por defecto, validación por etapa
contracts/               Tipos compartidos del protocolo (AgentInput/AgentResult)
orchestration/           Motor de decisión, registro de etapas
orchestration_langgraph/ Grafo de ejecución y enrutamiento condicional
runtime/                 Protocolo transaccional por etapa
state/                   Estado persistente, fingerprints
tools/                   Lógica de dominio de cada etapa
```

## Ejecutar el pipeline

En la práctica, corre `Corrida_03_a_08.ipynb` (parte del paquete de
notebooks) — arma el comando y gestiona la evaluación parcial de 08 por
vos. Ese notebook invoca directamente:

```bash
python3 -m src.orchestration_langgraph.pipeline_graph \
  --project-dir /ruta/a/PROJECT_DIR \
  --until 08_evaluacion_experimental
```

- Hasta una etapa específica: agregar `--until 07_agente_verificador`.
- Reintentar una sola etapa desde un estado terminal: `--start-stage <etapa>`.
- Reinicio limpio (cambio de código, o corrida anterior interrumpida):
  `--fresh-start`. El pipeline también detecta cambios de código por su
  cuenta y hace este reinicio automáticamente cuando hace falta.

Ver `README.md` sección 4 para el detalle completo de flags.

## Las etapas, en orden

```
03  Extracción de fichas científicas
03B Normalización y verificación cuantitativa
04  Análisis temático
05  Generación del esquema
06  Redacción basada en evidencia
07  Verificación factual  ──┐
     └──── RETURN a 06 ─────┘   (ciclo de revisión, hasta 3 rondas)
08  Evaluación experimental
```

## Configuración

Todo lo que el orquestador necesita vive en un único archivo,
`active_experiment.json`, escrito por el notebook `00_setup_config`: modelo
generativo, modelo de embeddings, perfil de generación (idioma, extensión,
estilo), y la política de recuperación (RAG_POLICY) con sus perfiles y
umbral mínimo de relevancia. Ningún módulo de `src/` mantiene una copia
separada de esta configuración — cuando una etapa necesita derivar algo
más elaborado a partir de ella, lo hace en tiempo real desde el mismo
archivo, nunca desde una copia local.

## Qué esperar de una corrida

Una ejecución completa puede terminar aprobada para publicación, o en
`PARTIAL_HALT` con al menos una afirmación marcada para revisión manual —
este segundo desenlace es un resultado válido y esperado del diseño: el
sistema prefiere derivar a revisión humana antes que forzar un veredicto
automático cuando la evidencia disponible no permite resolver una
afirmación con confianza suficiente. Ver `README.md` sección 8.

## Dónde mirar para más detalle

| Tema | Sección del README |
|---|---|
| El paquete de notebooks | 2 |
| Estructura de `src/` | 3.2 |
| Ciclo de escritura-verificación (06↔07) | 3.3 |
| Recuperación adaptativa de evidencia | 3.4 |
| Estado transaccional y reproducibilidad | 3.6 |
| Configuración del experimento | 5 |
| Outputs por etapa | 6 |
| Métricas de evaluación | 7 |
| Consideraciones para nuevos dominios/corpus | 9 |
