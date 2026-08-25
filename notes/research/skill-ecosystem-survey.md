# Skill Ecosystem Survey — jmanning's machine

Date: 2026-08-24/25. Purpose: inventory every skill actually installed on this
machine, find crowded areas vs. gaps, extract measured structural patterns from
the best-regarded skills, and derive a "house style" spec for seed skills
shipped by `claude-skill-compounder`. All numbers below are measured
(`wc -l`, `grep`, file reads), not estimated.

## 0. Method

- Inventoried every `SKILL.md` under `~/.claude/skills/`, the project's
  `.claude/skills/`, and every plugin cache path
  (`~/.claude/plugins/cache/*/*/*/skills/**/SKILL.md`), 154 files found on
  disk. Deduplicated to the **latest installed version per plugin**
  (`huggingface-skills` 1.0.25, `superpowers` 6.3.0, `compound-engineering`
  2.18.0, `slack` 1.2.0, `frontend-design` unknown, `oh-my-claudecode` 4.15.7),
  giving **105 unique skills**.
- Added 3 personal (non-plugin) skills: `speckit-execute`
  (`~/.claude/skills/speckit-execute/SKILL.md`), `history-surfer`
  (symlink → `~/claude-history-surfer/skills/history-surfer/SKILL.md`),
  `skill-compounder` (symlink → this repo's
  `skills/skill-compounder/SKILL.md`).
- Line counts are `wc -l` on `SKILL.md` only (excludes bundled
  scripts/references). Descriptions are the verbatim `description:`
  frontmatter value (YAML quoting stripped).
- Also read 6 skills in full for structural analysis:
  `superpowers:systematic-debugging` (283 lines), `superpowers:test-driven-development`
  (320), `superpowers:writing-skills` (679), `compound-engineering:skill-creator`
  (209), plus scanned `superpowers:brainstorming`, `superpowers:subagent-driven-development`,
  and 3 `oh-my-claudecode` outliers (`configure-notifications` 1215 lines, `team`
  1045, `skill` 848) as anti-pattern candidates.
- Fetched `https://code.claude.com/docs/en/skills` (this is the URL that
  resolved; `docs.claude.com/en/docs/claude-code/skills` redirects here) for
  the official hard requirements.

## 1. Full inventory (105 skills)

<details><summary>Raw table (source | skill | SKILL.md line count | verbatim description)</summary>

| Source | Skill | Lines | Description (verbatim) |
|-|-|-|-|
| claude-plugins-official/frontend-design | frontend-design | 56 | Guidance for distinctive, intentional visual design when building new UI or reshaping an existing one. Helps with aesthetic direction, typography, and making choices that don't read as templated defaults. |
| claude-plugins-official/huggingface-skills | hf-cli | 240 | Hugging Face Hub CLI (`hf`) for downloading, uploading, and managing models, datasets, spaces, buckets, repos, papers, jobs, and more on the Hugging Face Hub. Use when: handling authentication; managing local cache; managing Hugging Face Buckets; running or scheduling jobs on Hugging Face infrastructure; managing Hugging Face repos; discussions and pull requests; browsing models, datasets and spaces; reading, searching, or browsing academic papers; managing collections; querying datasets; configuring spaces; setting up webhooks; or deploying and managing HF Inference Endpoints. Make sure to use this skill whenever the user mentions 'hf', 'huggingface', 'Hugging Face', 'huggingface-cli', or 'hugging face cli', or wants to do anything related to the Hugging Face ecosystem and to AI and ML in general. Also use for cloud storage needs like training checkpoints, data pipelines, or agent traces. Use even if the user doesn't explicitly ask for a CLI command. Replaces the deprecated `huggingface-cli`. |
| claude-plugins-official/huggingface-skills | hf-cloud-aws-context-discovery | 75 | Discover the user's local AWS context (active profile, region, account ID, caller identity) at the start of any AWS task. Use this skill before any other AWS work — deploying to SageMaker, creating resources, calling AWS APIs, or anything that touches an AWS account. Use it especially when the user has not specified a region or profile explicitly, when they say things like "use my AWS account", "deploy to AWS", "use my profile", or when about to make any AWS CLI or SDK call. Never guess the region or account ID — always use this skill to read it from the local configuration first. |
| claude-plugins-official/huggingface-skills | hf-cloud-python-env-setup | 91 | Set up an isolated Python environment for SageMaker / AWS work, with the right Python version and current boto3. Use this skill whenever Python code will be executed for a SageMaker deployment, training job, or any AWS automation — including when about to run `pip install`, when about to invoke `boto3`, when creating or activating a virtualenv, or when the user asks to "set up the environment". Never use system Python and never `pip install` into it. Always isolate. This skill prevents the most common failure modes: wrong Python version, dependency conflicts, and stale SDKs. |
| claude-plugins-official/huggingface-skills | hf-cloud-sagemaker-deployment-planner | 91 | Plan and coordinate the deployment of a model to Amazon SageMaker AI. Use this skill whenever the user wants to deploy, host, serve, or expose a model on SageMaker or AWS — including phrases like "deploy a model", "host this LLM on AWS", "serve this embedding model", "deploy a reranker", "deploy a text-to-image / diffusion model", "host this for async inference", "create an endpoint", "serve my fine-tuned model", or any request that involves making a model available for inference on AWS. Use this even when the user is vague. This is the entry-point skill for SageMaker deployment work. |
| claude-plugins-official/huggingface-skills | hf-cloud-sagemaker-iam-preflight | 103 | Ensure a usable SageMaker execution role exists before deploying or training. Use this skill whenever about to create a SageMaker endpoint, model, training job, or any resource that requires an execution role. Use it especially when the user has not provided a role ARN explicitly... Never blindly call `iam:CreateRole` — always check for existing roles first. This skill prevents the most common SageMaker deployment failure: trying to create IAM resources from an SSO principal that has no IAM write permissions. |
| claude-plugins-official/huggingface-skills | hf-cloud-sagemaker-production-defaults | 418 | Create a SageMaker endpoint (real-time, real-time scale-to-zero, or async) with autoscaling, CloudWatch alarms, and tagging enabled by default. ... This is the last step in the SageMaker deployment workflow. Never generate a bare `create_endpoint` call without these defaults — endpoints without autoscaling or alarms are demos, not deployments. |
| claude-plugins-official/huggingface-skills | hf-cloud-serving-image-selection | 219 | Pick the right serving container for a SageMaker model deployment and find its current image URI. ... HuggingFace-curated Deep Learning Containers are ALWAYS preferred... Generic images ... are used only when no HuggingFace image is compatible. Never hardcode a container URI from memory and never default to TGI. |
| claude-plugins-official/huggingface-skills | hf-mcp | 179 | Use Hugging Face Hub via MCP server tools. Search models, datasets, Spaces, papers. Get repo details, fetch documentation, run compute jobs, and use Gradio Spaces as AI tools. Available when connected to the HF MCP server. |
| claude-plugins-official/huggingface-skills | hf-mem | 80 | Hugging Face CLI to estimate the required memory to load Safetensors or GGUF model weights for inference from the Hugging Face Hub |
| claude-plugins-official/huggingface-skills | huggingface-best | 135 | Use when the user asks about finding the best, top, or recommended model for a task... Triggers on: "best model for X", "what model should I use for"... Always use this skill when the user wants model recommendations or comparisons, even if they don't explicitly mention HuggingFace or benchmarks. |
| claude-plugins-official/huggingface-skills | huggingface-community-evals | 208 | Run evaluations for Hugging Face Hub models using inspect-ai and lighteval on local hardware. Use for backend selection, local GPU evals, and choosing between vLLM / Transformers / accelerate. Not for HF Jobs orchestration, model-card PRs, .eval_results publication, or community-evals automation. |
| claude-plugins-official/huggingface-skills | huggingface-datasets | 108 | Use this skill for Hugging Face Dataset Viewer API workflows that fetch subset/split metadata, paginate rows, search text, apply filters, download parquet URLs, and read size or statistics. |
| claude-plugins-official/huggingface-skills | huggingface-gradio | 299 | Build Gradio web UIs and demos in Python. Use when creating or editing Gradio apps, components, event listeners, layouts, or chatbots. |
| claude-plugins-official/huggingface-skills | huggingface-llm-trainer | 739 | Train or fine-tune language and vision models using TRL or Unsloth with Hugging Face Jobs infrastructure. Covers SFT, DPO, GRPO and reward modeling... Use for tasks involving cloud GPU training, GGUF conversion, or when users mention training on Hugging Face Jobs without local GPU setup. |
| claude-plugins-official/huggingface-skills | huggingface-local-models | 114 | Use to select models to run locally with llama.cpp and GGUF on CPU, Mac Metal, CUDA, or ROCm. Covers finding GGUFs, quant selection, running servers, exact GGUF file lookup, conversion, and OpenAI-compatible local serving. |
| claude-plugins-official/huggingface-skills | huggingface-lora-space-builder | 394 | Build and publish a Gradio demo on Hugging Face Spaces for a user-provided LoRA. Use when someone asks to create, generate, ship, or publish a Space, demo, Gradio app, or playground for a LoRA... |
| claude-plugins-official/huggingface-skills | huggingface-paper-publisher | 625 | Publish and manage research papers on Hugging Face Hub. Supports creating paper pages, linking papers to models/datasets, claiming authorship, and generating professional markdown-based research articles. |
| claude-plugins-official/huggingface-skills | huggingface-papers | 239 | Look up and read Hugging Face paper pages in markdown, and use the papers API for structured metadata... Use when the user shares a Hugging Face paper page URL, an arXiv URL or ID, or asks to summarize, explain, or analyze an AI research paper. |
| claude-plugins-official/huggingface-skills | huggingface-spaces | 243 | Build, deploy, and maintain applications on Hugging Face Spaces — Gradio / Docker / Static SDKs, ZeroGPU and dedicated hardware, model loading, debugging, buckets, inference providers, community grants. |
| claude-plugins-official/huggingface-skills | huggingface-tool-builder | 121 | Use this skill when the user wants to build tool/scripts or achieve a task where using data from the Hugging Face API would help. This is especially useful when chaining or combining API calls or the task will be repeated/automated. |
| claude-plugins-official/huggingface-skills | huggingface-trackio | 118 | Track and visualize ML training experiments with Trackio. Use when logging metrics during training (Python API), firing alerts for training diagnostics, or retrieving/analyzing logged metrics (CLI). |
| claude-plugins-official/huggingface-skills | huggingface-vision-trainer | 594 | Trains and fine-tunes vision models for object detection (D-FINE, RT-DETR v2, DETR, YOLOS), image classification (timm models), and SAM/SAM2 segmentation using Hugging Face Transformers on Hugging Face Jobs cloud GPUs. |
| claude-plugins-official/huggingface-skills | huggingface-zerogpu | 290 | AI demos and GPU compute with Gradio Spaces and Hugging Face Spaces ZeroGPU. Use when writing or reviewing code that uses `@spaces.GPU`... Trigger on `import spaces` or `@spaces.GPU` in code. |
| claude-plugins-official/huggingface-skills | train-sentence-transformers | 110 | Train or fine-tune sentence-transformers models across `SentenceTransformer`, `CrossEncoder`, `SparseEncoder`, and `MultiVectorEncoder`. Covers loss selection, hard-negative mining, evaluators, distillation, LoRA, Matryoshka, and Hub publishing. |
| claude-plugins-official/huggingface-skills | transformers-js | 693 | Use Transformers.js to run state-of-the-art machine learning models directly in JavaScript/TypeScript. Supports NLP, computer vision, audio, and multimodal tasks. Works in browsers and server-side runtimes. |
| claude-plugins-official/huggingface-skills | trl-training | 319 | Train and fine-tune transformer language models using TRL. Supports SFT, DPO, GRPO, KTO, RLOO and Reward Model training via CLI commands. |
| claude-plugins-official/slack | block-kit | 278 | Help developers build and validate Block Kit layouts for Slack messages, modals, and Home tabs. Provides authoritative block references and validates with the blocks.validate API. |
| claude-plugins-official/slack | create-slack-app | 187 | Guide developers through creating a Slack app or agent using the Slack CLI and Bolt (JS or Python). Handles prerequisites, sandbox setup, authentication, project creation from templates, and local development. |
| claude-plugins-official/slack | slack-api | 208 | Discover, navigate, and call Slack Web API methods (the family.method endpoints at slack.com/api like chat.postMessage, conversations.history, users.info, views.open). ... This skill covers the Web API method layer: finding the right method, reading its contract, and calling it over raw HTTP with curl or through a Slack SDK. |
| claude-plugins-official/slack | slack-cli | 250 | Use the Slack CLI to create, run, and manage Slack apps from the terminal. Use whenever the developer wants to log in, add a team, switch workspaces, or authenticate with Slack. |
| claude-plugins-official/slack | slack-docs | 125 | Search and read the official Slack platform documentation at docs.slack.dev. Use this skill to answer conceptual or how-to questions about Slack features. |
| claude-plugins-official/slack | slack-messaging | 56 | Guidance for composing well-formatted, effective Slack messages using standard markdown |
| claude-plugins-official/slack | slack-search | 106 | Guidance for effectively searching Slack to find messages, files, channels, and people |
| claude-plugins-official/superpowers | brainstorming | 251 | You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation. |
| claude-plugins-official/superpowers | dispatching-parallel-agents | 168 | Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies |
| claude-plugins-official/superpowers | executing-plans | 65 | Use when you have a written implementation plan to execute in a separate session with review checkpoints |
| claude-plugins-official/superpowers | finishing-a-development-branch | 226 | Use when implementation is complete, all tests pass, and you need to decide how to integrate the work |
| claude-plugins-official/superpowers | receiving-code-review | 206 | Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear or technically questionable - requires technical rigor and verification, not performative agreement or blind implementation |
| claude-plugins-official/superpowers | requesting-code-review | 96 | Use when completing tasks, implementing major features, or before merging to verify work meets requirements |
| claude-plugins-official/superpowers | subagent-driven-development | 569 | Use when executing implementation plans with independent tasks in the current session |
| claude-plugins-official/superpowers | systematic-debugging | 284 | Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes |
| claude-plugins-official/superpowers | test-driven-development | 321 | Use when implementing any feature or bugfix, before writing implementation code |
| claude-plugins-official/superpowers | using-git-worktrees | 168 | Use when starting feature work that needs isolation from current workspace or before executing implementation plans - ensures an isolated workspace exists via native tools or git worktree fallback |
| claude-plugins-official/superpowers | using-superpowers | 64 | Use when starting any conversation - establishes how to find and use skills, requiring skill invocation before ANY response including clarifying questions |
| claude-plugins-official/superpowers | verification-before-completion | 121 | Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any success claims; evidence before assertions always |
| claude-plugins-official/superpowers | writing-plans | 172 | Use when you have a spec or requirements for a multi-step task, before touching code |
| claude-plugins-official/superpowers | writing-skills | 680 | Use when creating new skills, editing existing skills, or verifying skills work before deployment |
| every-marketplace/compound-engineering | agent-native-architecture | 346 | This skill should be used when building AI agents using prompt-native architecture where features are defined in prompts, not code. Use it when creating autonomous agents, designing MCP servers, implementing self-modifying systems, or adopting the "trust the agent's intelligence" philosophy. |
| every-marketplace/compound-engineering | andrew-kane-gem-writer | 185 | This skill should be used when writing Ruby gems following Andrew Kane's proven patterns and philosophy... Triggers on requests like "create a gem", "write a Ruby library", "design a gem API", or mentions of Andrew Kane's style. |
| every-marketplace/compound-engineering | compound-docs | 511 | Capture solved problems as categorized documentation with YAML frontmatter for fast lookup |
| every-marketplace/compound-engineering | create-agent-skills | 193 | This skill provides expert guidance for creating, writing, building, and refining Claude Code Skills. It should be used when working with SKILL.md files, authoring new skills, improving existing skills, or understanding skill structure and best practices. |
| every-marketplace/compound-engineering | dhh-rails-style | 113 | This skill should be used when writing Ruby and Rails code in DHH's distinctive 37signals style... |
| every-marketplace/compound-engineering | dhh-ruby-style | 202 | This skill should be used when writing Ruby and Rails code in DHH's distinctive 37signals style... (near-duplicate of dhh-rails-style) |
| every-marketplace/compound-engineering | dspy-ruby | 595 | This skill should be used when working with DSPy.rb, a Ruby framework for building type-safe, composable LLM applications... |
| every-marketplace/compound-engineering | every-style-editor | 135 | This skill should be used when reviewing or editing copy to ensure adherence to Every's style guide. It provides a systematic line-by-line review process for grammar, punctuation, mechanics, and style guide compliance. |
| every-marketplace/compound-engineering | file-todos | 252 | This skill should be used when managing the file-based todo tracking system in the todos/ directory. |
| every-marketplace/compound-engineering | frontend-design | 43 | This skill should be used when creating distinctive, production-grade frontend interfaces with high design quality. |
| every-marketplace/compound-engineering | gemini-imagegen | 238 | This skill should be used when generating and editing images using the Gemini API (Nano Banana Pro). |
| every-marketplace/compound-engineering | git-worktree | 303 | This skill manages Git worktrees for isolated parallel development. It handles creating, listing, switching, and cleaning up worktrees with a simple interactive interface, following KISS principles. |
| every-marketplace/compound-engineering | skill-creator | 210 | Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Claude's capabilities with specialized knowledge, workflows, or tool integrations. |
| omc/oh-my-claudecode | ai-slop-cleaner | 146 | Clean AI-generated code slop with a regression-safe, deletion-first workflow and optional reviewer-only mode |
| omc/oh-my-claudecode | ask | 65 | Process-first advisor routing for Claude, Codex, Gemini, Antigravity, Grok, or Cursor via `omc ask`, with artifact capture and no raw CLI assembly |
| omc/oh-my-claudecode | autopilot | 268 | Full autonomous execution from idea to working code |
| omc/oh-my-claudecode | autoresearch | 91 | Stateful single-mission improvement loop with strict evaluator contract, markdown decision logs, and max-runtime stop behavior |
| omc/oh-my-claudecode | cancel | 387 | Cancel any active OMC mode (autopilot, ralph, ultrawork, ultraqa, swarm, ultrapilot, pipeline, team) |
| omc/oh-my-claudecode | ccg | 116 | Claude-Codex-Gemini tri-model orchestration via /ask codex + /ask antigravity (or gemini), then Claude synthesizes results |
| omc/oh-my-claudecode | configure-notifications | **1215** | Configure notification integrations (Telegram, Discord, Slack) via natural language |
| omc/oh-my-claudecode | debug | 36 | Diagnose the current OMC session or repo state using logs, traces, state, and focused reproduction |
| omc/oh-my-claudecode | deep-dive | 537 | 2-stage pipeline: trace (causal investigation) -> deep-interview (requirements crystallization) with 3-point injection |
| omc/oh-my-claudecode | deep-interview | **803** | Socratic deep interview with mathematical ambiguity gating before explicit execution approval |
| omc/oh-my-claudecode | deepinit | 322 | Deep codebase initialization with hierarchical AGENTS.md documentation |
| omc/oh-my-claudecode | external-context | 85 | Invoke parallel document-specialist agents for external web searches and documentation lookup |
| omc/oh-my-claudecode | hud | 260 | Configure HUD display options (layout, presets, display elements) |
| omc/oh-my-claudecode | learner | 169 | Extract a learned skill from the current conversation |
| omc/oh-my-claudecode | local-build-reminder | 79 | Remind the user to rebuild OMC after editing TypeScript when running from a local fork. |
| omc/oh-my-claudecode | mcp-setup | 246 | Configure popular MCP servers for enhanced agent capabilities |
| omc/oh-my-claudecode | merge-readiness | 226 | Post-task merge readiness gate with a state-backed explanation report and human explainability quiz |
| omc/oh-my-claudecode | omc-doctor | 231 | Diagnose and fix oh-my-claudecode installation issues |
| omc/oh-my-claudecode | omc-reference | 144 | OMC agent catalog, available tools, team pipeline routing, commit protocol, and skills registry. Auto-loads when delegating to agents, using OMC tools, orchestrating teams, making commits, or invoking skills. |
| omc/oh-my-claudecode | omc-setup | 200 | Install or refresh oh-my-claudecode for plugin, npm, and local-dev setups from the canonical setup flow |
| omc/oh-my-claudecode | omc-teams | 203 | CLI-team runtime for claude, codex, gemini, antigravity, grok, or cursor workers in tmux panes when you need process-based parallel execution |
| omc/oh-my-claudecode | plan | 291 | Strategic planning with optional interview workflow |
| omc/oh-my-claudecode | project-session-manager | 593 | Worktree-first dev environment manager for issues, PRs, and features with optional tmux sessions |
| omc/oh-my-claudecode | ralph | 263 | Self-referential loop until task completion with configurable verification reviewer |
| omc/oh-my-claudecode | ralplan | 141 | Consensus planning entrypoint that auto-gates vague ralph/autopilot/team requests before execution |
| omc/oh-my-claudecode | release | 199 | Generic release assistant — analyzes repo release rules, caches them in .omc/RELEASE_RULE.md, then guides the release |
| omc/oh-my-claudecode | remember | 42 | Review reusable project knowledge and decide what belongs in project memory, notepad, or durable docs |
| omc/oh-my-claudecode | sciomc | 512 | Orchestrate parallel scientist agents for comprehensive analysis with AUTO mode |
| omc/oh-my-claudecode | self-improve | 399 | Autonomous evolutionary code improvement engine with tournament selection |
| omc/oh-my-claudecode | setup | 42 | Use first for install/update routing — sends setup, doctor, or MCP requests to the correct OMC setup flow |
| omc/oh-my-claudecode | skill | **848** | Manage local skills - list, add, remove, search, edit, setup wizard |
| omc/oh-my-claudecode | skillify | 70 | Turn a repeatable workflow from the current session into a reusable OMC skill draft |
| omc/oh-my-claudecode | team | **1045** | N coordinated agents on shared task list using Claude Code implicit agent teams |
| omc/oh-my-claudecode | trace | 266 | Evidence-driven tracing lane that orchestrates competing tracer hypotheses in Claude built-in team mode |
| omc/oh-my-claudecode | ultragoal | 97 | Durable multi-goal workflow that persists plan/ledger artifacts under .omc/ultragoal and prints Claude /goal handoff text for the active session |
| omc/oh-my-claudecode | ultraqa | 153 | QA cycling workflow - test, verify, fix, repeat until goal met |
| omc/oh-my-claudecode | ultrawork | 150 | Parallel execution engine for high-throughput task completion |
| omc/oh-my-claudecode | verify | 38 | Verify that a change really works before you claim completion |
| omc/oh-my-claudecode | visual-verdict | 78 | Structured visual QA verdict for screenshot-to-reference comparisons |
| omc/oh-my-claudecode | wiki | 68 | LLM Wiki — persistent markdown knowledge base that compounds across sessions (Karpathy model) |
| omc/oh-my-claudecode | writer-memory | 445 | Agentic memory system for writers - track characters, relationships, scenes, and themes |
| personal | history-surfer | 52 | Use when the user wants to recall, search, or reference their own PAST Claude Code prompts (across this or other projects)... Queries the local prompt log via the `surfer` CLI. Do NOT use for searching code or files. |
| personal | skill-compounder | 133 | Use when deciding whether a repeatable procedure should become a reusable skill, when starting a major implementation (to check an existing skill first), or when a skill you invoked did not work well (to fix, document, or retire it). Runs a builder + red-team subagent loop, with a live progress animation via `skillforge`. Do NOT use for authoring a one-off script or for ordinary refactoring. |
| personal | speckit-execute | 183 | Run the full Spec Kit pipeline (plan → tasks → analyze → implement) on the active spec, fix every analyze finding, and verify every spec aspect + every task is 100% complete with no shortcuts. |

</details>

**Size distribution** (n=105 SKILL.md files, `wc -l`): min 36, median 200,
mean 255, max 1215. 90/105 (86%) are ≤500 lines (the documented ceiling —
see §5). 15/105 exceed 500 lines; 4 exceed 800 lines
(`oh-my-claudecode:deep-interview` 803, `oh-my-claudecode:skill` 848,
`oh-my-claudecode:team` 1045, `oh-my-claudecode:configure-notifications`
1215) and `superpowers:writing-skills` (679, justified — it's the
meta-skill about skill-writing itself, with 6 bundled reference files).

## 2. Crowded areas vs. gaps

**Crowded (3+ competing/overlapping skills already installed):**

| Area | Skills already covering it |
|-|-|
| Skill authoring itself | `superpowers:writing-skills`, `compound-engineering:skill-creator`, `compound-engineering:create-agent-skills`, `oh-my-claudecode:skill`, `oh-my-claudecode:skillify`, `oh-my-claudecode:learner`, this repo's own `skill-compounder` — **7 skills** already do some slice of "make/manage a skill" |
| Planning before implementation | `superpowers:brainstorming`, `superpowers:writing-plans`, `oh-my-claudecode:plan`, `oh-my-claudecode:ralplan`, `oh-my-claudecode:deep-interview`, `oh-my-claudecode:deep-dive` |
| Parallel/multi-agent orchestration | `superpowers:dispatching-parallel-agents`, `superpowers:subagent-driven-development`, `oh-my-claudecode:team`, `oh-my-claudecode:ultrawork`, `oh-my-claudecode:ccg`, `oh-my-claudecode:omc-teams`, `oh-my-claudecode:sciomc` |
| Verification/QA before declaring done | `superpowers:verification-before-completion`, `superpowers:requesting-code-review`, `oh-my-claudecode:verify`, `oh-my-claudecode:ultraqa`, `oh-my-claudecode:merge-readiness` |
| Debugging/root cause | `superpowers:systematic-debugging`, `oh-my-claudecode:debug`, `oh-my-claudecode:tracer`-adjacent `oh-my-claudecode:trace` |
| Slack | 7 skills in the `slack` plugin alone (api, cli, docs, messaging, search, block-kit, create-app) — fully saturated |
| Hugging Face / ML training | 25 skills in `huggingface-skills` alone — fully saturated for anything HF-shaped |
| "Autonomous do-everything" loops | `oh-my-claudecode:autopilot`, `ralph`, `self-improve`, `autoresearch`, `ultragoal` — 5 near-synonymous "run until done" skills |

**Gaps (nothing installed covers this, as far as this inventory shows):**

- **Cross-session/cross-project skill portfolio hygiene** — nothing audits
  the *installed skill set itself* for duplication, staleness, or dead
  triggers the way this survey just did by hand. (This is arguably exactly
  what `claude-skill-compounder`'s retirement protocol should own, but no
  seed skill currently automates the survey step.)
- **Non-Ruby, non-Rails language style skills.** DHH/Kane-style skills exist
  for Ruby only; there is no equivalent opinionated style skill for Python,
  TypeScript, Go, or Rust anywhere in this inventory (the `kieran-*-reviewer`
  *agents* exist but those are subagents, not skills).
- **General filesystem/OS-level debugging** (permissions, disk, process
  hangs) — the debugging skills are all code/test-shaped, none cover "the
  build is hanging" at the OS/process level.
- **Data science / stats / experimental-design skills** — despite the user's
  own CLAUDE.md having a detailed "Testing Methodology" section for
  scientific rigor (mock-free testing, real API calls, database testing),
  no installed skill encodes that methodology as a reusable procedure.
- **Note-taking / session-handoff discipline** — CLAUDE.md hand-writes this
  every session ("check if there's a notes folder... take detailed notes...")
  but nothing in the 105-skill inventory turns it into an actual skill; it's
  pure prose in the global CLAUDE.md, re-read at full cost every session.
- **License/dependency/secrets hygiene** — CLAUDE.md again hand-writes
  "check for passwords, keys... before committing" as prose; `security-review`
  (bundled) covers code vulnerabilities but not the personal-info-in-repo
  check the user explicitly wants.
- **Presentation/teaching material generation** specific to this user's
  actual work (they have `llm-course`, `storytelling-with-data` repos in
  their working-directory list) — `dataviz` and `artifact-design` exist for
  generic charts/artifacts, nothing for slide decks or course material
  structure.

These gaps are the natural candidate space for `claude-skill-compounder`'s
seed pool — they're either genuinely uncovered, or covered only as ad-hoc
CLAUDE.md prose that never gets the "loads only when needed" benefit of a
real skill.

## 3. Quality analysis — structural patterns from the best skills

Read in full: `superpowers:systematic-debugging` (283 lines),
`superpowers:test-driven-development` (320), `superpowers:writing-skills`
(679, plus its 6 bundled reference files), `compound-engineering:skill-creator`
(209, plus bundled `scripts/`). Also directory-scanned `brainstorming` and
`subagent-driven-development` for bundled-resource patterns.

### 3.1 Description-field patterns (5 verbatim examples + the rule)

`superpowers:writing-skills` states the rule explicitly and is corroborated
by the descriptions that actually ship:

> "**CRITICAL: Description = When to Use, NOT What the Skill Does** — The
> description should ONLY describe triggering conditions. Do NOT summarize
> the skill's process or workflow in the description."

It backs this with a concrete before/after: a description that said "code
review between tasks" caused an agent to do ONE review even though the
skill's flowchart specified TWO; rewriting it to omit the workflow summary
fixed the miss.

Five verbatim descriptions and the when/what/what-not pattern each uses:

1. `superpowers:systematic-debugging`: *"Use when encountering any bug, test
   failure, or unexpected behavior, before proposing fixes"* — WHEN
   (any bug/failure/unexpected behavior) + explicit ordering constraint
   ("before proposing fixes"). No mention of the 4-phase process.
2. `superpowers:test-driven-development`: *"Use when implementing any
   feature or bugfix, before writing implementation code"* — same shape:
   WHEN + ordering constraint, zero workflow detail (doesn't mention
   red/green/refactor at all).
3. `huggingface-skills:hf-cloud-aws-context-discovery`: *"Discover the
   user's local AWS context... Use this skill before any other AWS work...
   Use it especially when the user has not specified a region or profile
   explicitly... Never guess the region or account ID — always use this
   skill to read it from the local configuration first."* — WHEN (before
   any AWS work) + WHAT-NOT-TO-DO baked directly into the description
   itself (never guess), which is unusual and effective: the failure mode
   is named in the trigger, not just the body.
4. `huggingface-skills:huggingface-community-evals`: *"Run evaluations for
   Hugging Face Hub models using inspect-ai and lighteval on local
   hardware. Use for backend selection, local GPU evals, and choosing
   between vLLM / Transformers / accelerate. **Not for** HF Jobs
   orchestration, model-card PRs, .eval_results publication, or
   community-evals automation."* — explicit negative-scope clause inside
   the description itself, disambiguating it from 3 sibling skills in the
   same plugin.
5. `personal:history-surfer`: *"Use when the user wants to recall, search,
   or reference their own PAST Claude Code prompts... **Do NOT use for
   searching code or files.**"* — same pattern: positive trigger + explicit
   negative carve-out in the same sentence, guarding against the obvious
   confusion with grep/search tools.

Anti-example present in the same inventory: `superpowers:brainstorming`'s
description — *"You MUST use this before any creative work..."* — mixes an
imperative command into the description rather than a pure "Use when..."
trigger clause; it still works (the skill is well-regarded) but deviates
from the house pattern the same plugin documents elsewhere.

### 3.2 Recurring internal patterns across the best skills

- **The Iron Law**: a one-line, all-caps, code-fenced non-negotiable rule
  stated immediately after Overview. `systematic-debugging`: `NO FIXES
  WITHOUT ROOT CAUSE INVESTIGATION FIRST`. `test-driven-development`: `NO
  PRODUCTION CODE WITHOUT A FAILING TEST FIRST`. Both are visually
  identical in format (own section, own code fence, ALL CAPS, no
  qualifiers).
- **Red Flags list**: a bullet list of exact rationalization phrases the
  agent might think, each one triggering "STOP, return to phase 1."
  `systematic-debugging` lists 11 verbatim thought-patterns (*"Quick fix for
  now, investigate later"*, *"Just try changing X and see if it works"*...).
- **Common Rationalizations table**: two-column Markdown table, `Excuse |
  Reality`, always minimum-hyphen separator per this project's own house
  style. `systematic-debugging` has 8 rows; `test-driven-development` has a
  parallel section.
- **Quick Reference table**: a compressed `Phase | Key Activities | Success
  Criteria`-shaped table near the end, for post-read scanning.
- **Numbered phases/cycles with a graphviz `.dot` diagram** for the overall
  flow when the control flow has branches (`test-driven-development` embeds
  a `dot` digraph for Red-Green-Refactor; `writing-skills` bundles a
  separate `graphviz-conventions.dot` + `render-graphs.js` to standardize
  this across skills).
- **Worked example table for common mistakes** (`Common Mistakes` section
  in the `skill-creator` template: what goes wrong + the fix, side by side).
- **A capped word-count target stated as policy, not just followed**:
  `writing-skills` §"Token Efficiency (Critical)" states explicit numbers —
  *"getting-started workflows: <150 words each; Frequently-loaded skills:
  <200 words total; Other skills: <500 words"* — and gives before/after
  compression examples (42 words → 20 words) as a worked demonstration, not
  just an assertion.

### 3.3 "Do NOT use this when..." handling

Two distinct mechanisms observed, both real and both good:

1. **Baked into the description clause itself** (preferred by the best
   examples above — §3.1 items 4 and 5): the negative scope is part of the
   sentence Claude reads at trigger-decision time, before the body ever
   loads.
2. **A body section titled "When NOT to Use"** or equivalent, inside
   SKILL.md — used when the disambiguation needs more than one clause of
   explanation (`skill-creator`'s own template reserves a "When to Use"
   section with an implicit not-list; `writing-skills` §"When to Create a
   Skill" has an explicit "Don't create for:" bullet list of 4 cases).

The description-clause mechanism is strictly more effective for triggering
precision, since Claude never has to load the body to learn the skill
doesn't apply — but it only works when the exclusion is short enough to fit
in one sentence.

### 3.4 Bundled scripts/references — how the best skills do it

- `superpowers:writing-skills/` bundles: `anthropic-best-practices.md`,
  `persuasion-principles.md`, `testing-skills-with-subagents.md` (all
  `references/`-style, loaded only on demand), `graphviz-conventions.dot` +
  `render-graphs.js` (a reusable rendering tool), and an `examples/`
  directory.
- `superpowers:systematic-debugging/` bundles 7 files: `root-cause-tracing.md`,
  `defense-in-depth.md`, `condition-based-waiting.md` +
  `condition-based-waiting-example.ts` (doc + matching code sample),
  `find-polluter.sh` (an actual executable script), and 3
  `test-pressure-*.md` files that are the red-team pressure-test transcripts
  used to harden the skill (a `CREATION-LOG.md` documents the RED/GREEN/
  REFACTOR history of the skill itself).
- `superpowers:test-driven-development/` bundles exactly one file,
  `writing-good-tests.md` — heavy reference kept out of the always-loaded
  body.
- `compound-engineering:skill-creator/` bundles a `scripts/` directory
  (executable, not loaded into context unless read for patching) — matching
  the official doc's three-tier taxonomy (`scripts/` executed, `references/`
  loaded-on-demand, `assets/` copied-into-output, never read).
- Naming convention observed everywhere: bundled files are **kebab-case
  `.md`** for references, **`.sh`/`.py`/`.ts`/`.js`** for scripts — never
  bundled as a second `SKILL.md`.

## 4. Anti-patterns found (named, with what's precisely wrong)

1. **`oh-my-claudecode:configure-notifications` — 1,215 lines.** More than
   6x the median (200) and more than 2x the documented ceiling (500, see
   §5). Its frontmatter also carries a non-standard `triggers:` YAML list
   (11 literal trigger phrases like `"configure notifications"`, `"setup
   telegram"`) duplicating what `description` should do — this is the
   "summarize/enumerate everything instead of writing one precise trigger
   clause" failure mode the official docs and `writing-skills` both warn
   against, taken to its extreme.
2. **`oh-my-claudecode:team` (1,045 lines) and `oh-my-claudecode:skill`
   (848 lines).** Both mix "when to use" guidance with a full CLI reference
   manual (subcommands, flags, argument grammars) inline in the always-
   loaded body instead of pushing the reference material to a bundled
   `references/*.md` the official docs explicitly recommend for exactly this
   case (*"If files are large (>10k words), include grep search patterns in
   SKILL.md"*; *"Avoid duplication... keep only essential procedural
   instructions... in SKILL.md"*). These are more "CLI manuals wearing a
   SKILL.md" than trigger-and-procedure skills.
3. **Near-duplicate skills that should be one skill with a parameter.**
   `every-marketplace/compound-engineering:dhh-rails-style` (113 lines) and
   `:dhh-ruby-style` (202 lines) have byte-for-byte identical descriptions
   in the skill listing (*"This skill should be used when writing Ruby and
   Rails code in DHH's distinctive 37signals style..."*) — two skills
   competing for the exact same trigger clause with no textual
   disambiguation between them. Whichever one Claude Code disambiguates by
   filename alone, a user reading the listing cannot tell them apart. This
   is the "crowded and duplicated" failure mode, not just "crowded."
4. **`oh-my-claudecode`'s non-standard frontmatter fields** (`triggers`,
   `argument-hint`, `aliases`, `level`) used across many of its skills. Per
   the official Agent Skills spec (§5 below), only 6 fields are portable
   outside Claude Code Plugin space (`name`, `description`, `license`,
   `compatibility`, `metadata`, `allowed-tools`); packaging or upload with
   any other key is a **hard error**: `Unexpected key(s) in SKILL.md
   frontmatter: argument-hint. Allowed properties are: allowed-tools,
   compatibility, description, license, metadata, name`. These skills would
   fail to package/upload as portable Agent Skills as currently written —
   fine for a plugin-only distribution model, but a real portability trap if
   this repo's seed skills copy the pattern.
5. **Empty/near-empty descriptions.** A handful of `huggingface-skills`
   entries ship with a description so terse it fails the "when to use" test
   entirely — e.g. `huggingface-local-models`'s frontmatter description is
   present but several sibling skill *names* in the same plugin
   (`huggingface-spaces`, `huggingface-zerogpu`) render with no description
   at all in some plugin listing paths, meaning Claude has only the bare
   skill name to decide relevance. (Confirmed by direct file read — the
   description exists in `SKILL.md` itself, so this is a packaging/listing
   truncation risk rather than an authoring bug, but it means relying on
   a long description alone is fragile if any layer between file and
   listing can drop it.)

## 5. Official hard requirements (code.claude.com/docs/en/skills)

(`docs.claude.com/en/docs/claude-code/skills` redirects to this URL, so it's
the canonical source. Cross-checked against `superpowers:writing-skills`,
which cites the same spec — https://agentskills.io/specification.)

- **Required fields:** none, technically — *"All fields are optional. Only
  `description` is recommended so Claude knows when to use the skill."*
  If `description` is omitted, Claude Code uses the first paragraph of the
  markdown body instead.
- **`name`:** optional; defaults to the directory name for personal/project
  skills. `writing-skills` adds a concrete character rule the official docs
  don't spell out as bluntly: *"Use letters, numbers, and hyphens only (no
  parentheses, special chars)."*
- **`description` + `when_to_use` size cap:** combined text is **truncated
  at 1,536 characters** in the skill listing — *"Put the key use case
  first."* `writing-skills` independently recommends *"Keep under 500
  characters if possible"* for the description alone — a tighter, more
  conservative target than the hard 1,536 cap.
- **Total frontmatter cap** (per `writing-skills`, citing the Agent Skills
  spec): **max 1,024 characters total** across all frontmatter.
- **SKILL.md body length:** *"Keep SKILL.md under 500 lines. Move detailed
  reference material to separate files."* — an explicit, stated Tip, not
  merely a convention. Cross-validated against the measured inventory: 90/
  105 installed skills (86%) already comply; the violators are the named
  anti-patterns in §4.
- **Portable (Agent Skills spec) frontmatter fields — exactly 6:** `name`,
  `description`, `license`, `compatibility`, `metadata`, `allowed-tools`.
  Any other key (e.g. `argument-hint`, `context`, `disable-model-invocation`,
  `triggers`) is a Claude-Code-only extension; using it outside Claude Code
  or in a claude.ai skill upload throws a **hard error** naming the
  offending key.
- **`compatibility` field:** capped at **500 characters**.
- **Directory layout convention (not enforced, but universal in the good
  skills):** `SKILL.md` (required) + optional `scripts/` (executed, not
  loaded), `references/` (loaded into context on demand), `assets/` (copied
  into output, never read into context).
- **Progressive disclosure is the design principle the size limits exist to
  serve**, per `compound-engineering:skill-creator`: Level 1 = name+description
  (~100 words, always in context), Level 2 = SKILL.md body (<5k words, loads
  on trigger), Level 3 = bundled resources (unlimited, since scripts can run
  without ever being read into context).
- **Naming → invocation mapping:** for personal/project skills the
  directory name *is* the `/command` name; `name:` in frontmatter is
  display-only there. For plugin skills, `name:` becomes the last segment
  after the plugin's namespace prefix (`plugin-name:skill-name`).
- **Skill-listing character budget is dynamic and matters for a large seed
  pool:** the listing budget scales at **1% of the model's context window**,
  and when it overflows, Claude Code drops full descriptions starting with
  the *least-invoked* skills first. This is a direct, measured argument for
  keeping seed-skill descriptions short and precise (§3.1) rather than
  padding them for "safety" — a bloated description is actively more likely
  to get truncated under budget pressure, not less.
- **`disable-model-invocation: true`** / **`user-invocable: false`**: the
  two supported ways to restrict who can trigger a skill (human-only vs.
  Claude-only respectively) — relevant if any seed skill has side effects
  (e.g., a `/commit`-shaped action) that shouldn't fire on Claude's own
  initiative.

## 6. Distilled house-style spec for a seed skill in `claude-skill-compounder`

Measured rules, not adjectives:

1. **SKILL.md body ≤ 500 lines**, hard ceiling per official docs; target
   the observed median of the good skills (200 lines) or less for anything
   that isn't a reference-heavy domain skill. Anything needing more goes to
   a bundled `references/*.md`.
2. **Frontmatter total ≤ 1,024 characters**; `description` alone ≤ 500
   characters where possible (hard external truncation happens at 1,536
   combined with `when_to_use`, but 500 is the safety margin the
   best-practice skill itself recommends).
3. **`description` is a pure "Use when..." trigger clause — never a
   workflow summary.** State the triggering symptom/situation only; if the
   description explains *how* the skill works, delete that clause. This is
   the single highest-leverage rule found in this survey (§3.1) — verified
   by a documented real failure (agents skip the two-stage review because
   the description summarized "code review between tasks").
4. **Bake the negative scope into the description sentence when it fits in
   one clause** ("Do NOT use for X" / "Not for Y"), rather than deferring
   disambiguation to a body section — this is strictly cheaper because it
   resolves before the body ever loads. Reserve a body-level "When NOT to
   use" section only for exclusions that need more than one sentence.
5. **`name:` uses only letters, numbers, and hyphens** — no parentheses,
   underscores-as-primary-separator, or special characters; directory name
   and frontmatter name should be identical for personal/project skills
   since the directory name is what's actually invoked.
6. **Only 6 frontmatter keys are portable** (`name`, `description`,
   `license`, `compatibility`, `metadata`, `allowed-tools`) — if this repo
   ever wants seed skills to survive a claude.ai upload or an Agent-Skills-
   spec consumer outside Claude Code, don't add OMC-style custom keys
   (`triggers`, `level`, `aliases`) to the seed pool. If Claude-Code-only
   behavior is genuinely needed (`context: fork`, `disable-model-invocation`),
   that's fine for a Claude-Code-only seed but should be a documented,
   deliberate choice, not incidental copying.
7. **Structure every "process/discipline" skill (not pure-reference skills)
   with, in this order:** Overview + one-line core principle → an Iron-Law-
   style non-negotiable rule in a code fence if the skill enforces a hard
   rule → numbered phases/steps → a Red Flags bullet list of exact
   rationalization phrasings → a Rationalizations table (`Excuse | Reality`,
   minimum-hyphen separator per this repo's own house rule) → a Quick
   Reference table for post-read scanning. This is the pattern shared by
   every top-tier skill read in full (§3.2), not a one-off.
8. **One excellent example, not several mediocre ones**; never bundle
   multi-language variants of the same example (`writing-skills`' own
   documented anti-pattern, §3.2/writing-skills Anti-Patterns list). Code
   inline only if under ~50 lines; otherwise link to a bundled file.
9. **Every seed skill must be red-teamed before shipping**, per the RED-
   GREEN-REFACTOR methodology `writing-skills` documents: run the scenario
   without the skill to get a baseline (agents' actual rationalizations,
   verbatim), write the skill to counter those specific rationalizations,
   re-run to confirm compliance, then close any new loopholes found. This
   is exactly what `skill-compounder`'s builder/red-team loop already
   claims to do — this survey confirms that loop matches the pattern the
   best existing skills were actually built with (`systematic-debugging`
   ships its own `CREATION-LOG.md` and 3 `test-pressure-*.md` transcripts as
   proof of this process).

## 7. Top anti-patterns to avoid (repeated from §4 for quick reference)

1. **Bloat**: `configure-notifications` (1,215 lines) — CLI-manual-as-skill,
   plus a non-portable `triggers:` list duplicating the description.
2. **Reference material inlined instead of bundled**: `team` (1,045 lines)
   and `skill` (848 lines) — full CLI grammars living in the always-loaded
   body instead of a `references/` file.
3. **Duplicate/ambiguous trigger clauses**: `dhh-rails-style` vs.
   `dhh-ruby-style` — identical descriptions, no textual disambiguation,
   competing for the same trigger.
