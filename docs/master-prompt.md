<!-- English translation of the original German prompt (master-prompt.de.md), which Claude Code received verbatim. -->

STACK OVERRIDE (from Jens, takes precedence over section 9): Frontend uses Vue 3 + Vite + TypeScript + Tailwind CSS + Vue Router (no Next.js/React/shadcn). Pick Vue-compatible equivalents for React Flow (e.g. Vue Flow). Backend and math stack stay as written.

MASTER PROMPT – MODEL THINKING AI

Development of an intelligent multi-model analysis and decision platform

1. ROLE AND TASK

You act as an interdisciplinary development team made up of:

- Senior Software Architect
- AI/ML Engineer
- Data Scientist
- Computational Modeler
- System Dynamics Expert
- Game Theory Expert
- UX/UI Designer
- Full-Stack Developer
- Product Manager

Your task is to design, architect, implement and iteratively improve a production-ready application called:

MODEL THINKING AI – Multi-Model Intelligence Framework

The application is conceptually based on Scott E. Page's approach in "The Model Thinker".

It should help users analyse complex problems by systematically combining different models of thinking and computation.

IMPORTANT:
Do not implement a mere chatbot interface. Build a standalone analysis platform with structured data, mathematical models, simulations, visualisations and traceable results.

2. PRODUCT GOAL

The application must have the following core capability:

A user describes a problem in natural language.

The system:

1. Analyses the question.
2. Identifies the underlying problem.
3. Breaks it down into relevant influencing factors.
4. Recognises actors, variables and dependencies.
5. Selects suitable mathematical and conceptual models.
6. Builds several independent model perspectives.
7. Computes results where sufficient data is available.
8. Compares the results.
9. Develops alternative scenarios.
10. Generates traceable recommendations for action.

The framework must take different and possibly contradictory perspectives into account.

3. MODEL LIBRARY

Implement an extensible model library with the following 24 model families:

A. Distributions and mathematical models

1. Normal Distribution
2. Power Law / Long Tail
3. Linear Models
4. Concavity and Convexity
5. Value and Power Models

B. Networks and information models

6. Network Models
7. Broadcast, Diffusion and Contagion Models
8. Entropy Models
9. Random Walk Models
10. Path Dependence Models
11. Local Interaction Models
12. Lyapunov and Equilibrium Models

C. Dynamic and strategic models

13. Markov Models
14. System Dynamics
15. Threshold and Feedback Models
16. Spatial and Hedonic Choice Models
17. Game Theory
18. Cooperation Models
19. Collective Action Problems
20. Mechanism Design
21. Signaling Models
22. Learning Models
23. Multi-Armed Bandit Models
24. Rugged Landscape Models

Each model gets its own module with:

- model description
- mathematical definition
- input parameters
- prerequisites
- model assumptions
- calculation logic
- results
- visualisations
- application examples
- limits and risks

The mathematical implementations must run independently of the AI.

The AI may select and parameterise models, but must not invent calculation results.

4. INTELLIGENT MODEL SELECTION

Build a Model Selection Engine.

Based on the problem, it must decide:

- Which models are relevant?
- Which models complement each other?
- Which models provide different perspectives?
- Which models are unsuitable?
- What additional data is needed?

Models are selected by the following criteria:

1. Problem type
2. System complexity
3. Available data
4. Number of actors
5. Temporal dynamics
6. Uncertainty
7. Interactions
8. Decision relevance

Produce a Model Fit Score between 0 and 100.

This score is a transparent internal heuristic, not a statistically validated probability of fit.

Justify every model choice.

5. MULTI-MODEL ORCHESTRATION ENGINE

Build an engine that can run several models in parallel or in sequence.

The engine must:

- Detect model dependencies.
- Manage shared input parameters.
- Respect differing model assumptions.
- Store results in a standard format.
- Identify contradictions between models.
- Compare sensitivities.
- Show model limits transparently.

Create a shared result structure:

- problem definition
- model name
- model version
- input parameters
- assumptions
- calculation results
- uncertainty indicators
- scenarios
- interpretation
- recommendations for action

Avoid artificially merging incompatible model results.

6. SCENARIO ENGINE

Implement a scenario engine.

At least the following scenarios must be supported:

- Baseline Scenario
- Best Case
- Worst Case
- Alternative Scenario
- Stress Scenario
- What-if Scenario

Users must be able to change influencing parameters.

The system then computes the effects on the respective models.

Also implement:

- sensitivity analyses
- parameter comparisons
- Monte Carlo simulations where useful
- probability distributions
- uncertainty intervals where methodologically justified

Consistently distinguish between computed values, assumptions and AI-generated interpretations.

7. KNOWLEDGE GRAPH

Implement a knowledge graph that connects the following elements:

- problems
- actors
- variables
- influencing factors
- models
- hypotheses
- data sources
- results
- scenarios
- decisions

The graph should visualise relationships.

In particular, it must be able to show cause-and-effect relationships and feedback loops.

Correlations must not automatically be interpreted as causal relationships.

8. USER INTERFACE

Build a modern, professional and intuitive user interface.

Main navigation:

1. Dashboard
2. New Analysis
3. Problem Explorer
4. Model Library
5. Model Selection
6. Multi-Model Analysis
7. Scenario Lab
8. Simulation Center
9. Knowledge Graph
10. Decision Center
11. Reports
12. Settings

DASHBOARD:

Show:

- active analyses
- saved projects
- models used
- recent simulations
- key insights
- open decisions

NEW ANALYSIS:

Allow entering a problem in natural language.

Add structured fields for:

- objective
- time horizon
- system boundaries
- available data
- relevant actors
- scope for decisions

MODEL LIBRARY:

Each model gets its own detail page with:

- explanation
- mathematical basis
- visualisation
- input parameters
- examples
- use cases

MULTI-MODEL ANALYSIS:

Show the selected models side by side.

Compare their:

- results
- assumptions
- forecasts
- uncertainties
- recommendations for action

SCENARIO LAB:

Provide interactive parameter sliders and scenario comparisons.

DECISION CENTER:

Produce prioritised recommendations for action with:

- expected impact
- prerequisites
- risks
- uncertainty
- time horizon
- required measures

9. TECHNICAL ARCHITECTURE

Use a modular and scalable architecture.

Preferred technology stack:

Frontend:

- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui

(See STACK OVERRIDE above: Vue 3 instead of Next.js/React.)

Backend:

- Python
- FastAPI
- Pydantic

Mathematical computation:

- NumPy
- SciPy
- Pandas
- NetworkX
- SimPy
- scikit-learn

Data storage:

- PostgreSQL
- optionally pgvector
- Redis for caching and background processes

Visualisation:

- Plotly
- React Flow
- D3.js

AI integration:

- interchangeable LLM interface
- structured JSON outputs
- tool calling
- AI orchestration separated from calculation logic

The architecture must allow adding further models later.

10. DATA MODEL

Build at least the following database entities:

- User
- Workspace
- Project
- Analysis
- ProblemDefinition
- Actor
- Variable
- Model
- ModelVersion
- ModelExecution
- ModelParameter
- ModelResult
- Scenario
- Simulation
- Hypothesis
- Evidence
- Recommendation
- Report

Implement relationships, versioning and traceable storage of the analysis history.

11. AI ANALYSIS PROCESS

The AI must follow a structured analysis protocol:

PHASE 1 – UNDERSTAND
Understand and sharpen the problem.

PHASE 2 – DECOMPOSE
Break the problem down into sub-problems, variables and actors.

PHASE 3 – SELECT
Identify suitable models and justify the choice.

PHASE 4 – PARAMETERIZE
Determine the required parameters and data.

PHASE 5 – EXECUTE
Run the mathematical models.

PHASE 6 – COMPARE
Compare results and model perspectives.

PHASE 7 – SIMULATE
Compute scenarios and alternative developments.

PHASE 8 – SYNTHESIZE
Integrate insights from different models.

PHASE 9 – DECIDE
Derive options and recommendations for action.

PHASE 10 – EVALUATE
Check results against new data and improve the models.

12. QUALITY AND VALIDATION

Every model needs:

- unit tests
- integration tests
- mathematical plausibility checks
- boundary-value tests
- reproducible simulations
- traceable calculation logs

Use known test cases and analytic reference solutions.

Flag insufficient data and unvalidated model assumptions.

The platform must not create false precision.

13. SECURITY

Implement:

- secure authentication
- role-based access rights
- data encryption
- secure API communication
- audit logs
- protection against prompt injection
- validation of all inputs
- separate storage for different tenants

14. DEVELOPMENT STRATEGY

Implement the project incrementally.

PHASE 1 – FOUNDATION
- system architecture
- data model
- user interface
- model library
- first five models

PHASE 2 – ANALYTICS
- complete model library
- Model Selection Engine
- multi-model orchestration

PHASE 3 – SIMULATION
- Scenario Engine
- Monte Carlo simulation
- sensitivity analysis
- interactive visualisation

PHASE 4 – INTELLIGENCE
- AI analysis
- knowledge graph
- Decision Center
- automated reports

PHASE 5 – PRODUCTION
- security
- performance
- monitoring
- automated tests
- deployment

15. HOW THE CODING AGENT WORKS

Do not work only conceptually.

Produce actually executable and tested code.

Start with:

1. architecture decision
2. system structure
3. database schema
4. API design
5. UI concept
6. implementation plan

Then implement the application step by step.

After each development phase:

- run the code
- run the tests
- fix bugs
- update the documentation
- record the implementation status

Avoid non-functional placeholders and simulated results presented as real model calculations.

If a feature is not implemented yet, flag it transparently.

16. DEFINITION OF DONE

The application only counts as functional when:

- A problem can be entered.
- The system structures the problem.
- Models are proposed automatically.
- At least five models are actually executed mathematically.
- Several model results are compared.
- Parameters can be changed.
- Scenarios are computed.
- Results are visualised.
- Recommendations for action are derived traceably.
- Analyses can be saved and reopened.
- Automated tests pass.

FINAL GUIDELINE

Do not build an application that merely summarises existing information.

Build a real multi-model decision intelligence system.

The core value is the ability to examine complex problems from several mathematically different perspectives, compare the results critically and derive better decisions from them.

Start with the architecture and a working MVP. Deliver runnable results after each development phase instead of just more planning.
