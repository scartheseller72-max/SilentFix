# SilentFix

**Automated Detection, Localization, and Repair of Silent Logic Errors in Python**

SilentFix is an end-to-end automated program repair system that targets *silent bugs* — logic errors that produce incorrect outputs without raising exceptions or triggering observable failures. Unlike traditional APR tools that require failing test suites as oracles, SilentFix infers behavioral specifications directly from source code, then uses those specifications to detect violations, localize faults, and synthesize minimal patches.

```
Property Inference --> Bug Detection --> Execution Tracing --> Fault Localization --> Patch Synthesis --> Validation
```

> **Key insight.** A function's name, type annotations, docstring, and dynamic behavior collectively encode enough semantic information to serve as an implicit specification — even in the absence of any test suite.

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Approach Overview](#approach-overview)
- [Architecture](#architecture)
  - [Phase 1: Property Inference](#phase-1-property-inference)
  - [Phase 2: Bug Detection](#phase-2-bug-detection)
  - [Phase 3: Execution Tracing](#phase-3-execution-tracing)
  - [Phase 4: Fault Localization](#phase-4-fault-localization)
  - [Phase 5: Patch Synthesis](#phase-5-patch-synthesis)
  - [Phase 6: Validation](#phase-6-validation)
- [Installation](#installation)
- [Usage](#usage)
  - [Python API](#python-api)
  - [Command-Line Interface](#command-line-interface)
- [Configuration](#configuration)
- [LLM Backend Setup](#llm-backend-setup)
- [Evaluation](#evaluation)
- [Project Structure](#project-structure)
- [Data Types and API Reference](#data-types-and-api-reference)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

---

## Problem Statement

Consider a standard `max` implementation with a subtle initialization error:

```python
def buggy_max(a: list[int]) -> int:
    result = 0
    for x in a:
        if x > result:
            result = x
    return result
```

This function works correctly on any list containing at least one non-negative element. However, `buggy_max([-5, -3, -1])` returns `0` rather than the correct answer `-1`. No exception is raised. No type error occurs. If a test suite does not include an all-negative input, the bug persists silently in production.

These are **silent logic errors**: semantically incorrect behavior that is invisible to crash-based monitoring, type checkers, and incomplete test suites. They are a well-studied category in the software engineering literature (see Papadakis et al., 2019; Le Goues et al., 2019) and remain one of the most difficult classes of defects to detect automatically.

SilentFix addresses this problem with a fully automated pipeline that requires no tests, no formal specifications, and no human-written oracles.

---

## Approach Overview

SilentFix operates in six sequential phases:

1. **Property Inference** — Extracts behavioral specifications (preconditions, postconditions, invariants, metamorphic relations) from five independent sources and fuses them via confidence-weighted voting.

2. **Bug Detection** — Searches for concrete inputs that violate inferred properties using property-based testing, symbolic execution, and statistical outlier detection.

3. **Execution Tracing** — Instruments the target function via `sys.settrace` to collect fine-grained execution traces (line-level coverage, variable snapshots, branch decisions) for both passing and failing inputs.

4. **Fault Localization** — Ranks source lines by suspiciousness using a weighted combination of spectrum-based fault localization (SBFL) and KL-divergence analysis of variable distributions over passing vs. failing traces.

5. **Patch Synthesis** — Generates candidate repairs via a three-tier escalation strategy: template-based fixes, Z3 constraint synthesis, and LLM-guided repair.

6. **Validation** — Verifies each candidate patch against regression tests and property re-verification.

The system returns a `RepairResult` containing the best validated patch, all inferred properties, the set of bug-triggering inputs, and ranked fault localization results.

---

## Architecture

### Phase 1: Property Inference

The property inference subsystem extracts behavioral specifications from five independent sources and combines them into a unified `PropertySet`. Each source produces properties tagged with a confidence score and provenance label.

**Source 1: Static Extraction** (`property_inference/static_extractor.py`)

Performs AST-level analysis of the function's name, signature, type hints, docstring, and inline comments. Name-based heuristics map common naming conventions to expected behavior:

- Functions containing `max` in the name produce a postcondition asserting `output == max(input)`.
- Functions containing `sort` produce postconditions for ordering and length preservation.
- Docstring keywords (`"sum"`, `"average"`, `"unique"`, `"reverse"`, `"filter"`, `"idempotent"`) trigger corresponding postconditions.
- Inline comments containing `"expects"`, `"requires"`, or `"assumes"` generate preconditions.

Type hints contribute type-level postconditions (e.g., `-> bool` implies `isinstance(output, bool)`).

**Source 2: Type Inference** (`property_inference/type_inferrer.py`)

Generates properties exclusively from return type annotations:

- Collection return types (`list`, `tuple`, `Sequence`) produce non-negative length assertions and input/output length bounds.
- Primitive return types (`int`, `float`, `bool`, `dict`) produce `isinstance` postconditions.
- `Optional[T]` and `T | None` annotations produce nullable-output properties.

**Source 3: Dynamic Mining** (`property_inference/dynamic_miner.py`)

Executes the target function on a configurable number of randomly generated inputs (default: 200) and mines invariants from observed input-output pairs:

- **Numeric relationships**: non-negativity, non-positivity, boundedness, `output == max(input)`, `output == min(input)`, `output == sum(input)`, identity (`output == input`).
- **Collection relationships**: non-empty output, output length equals input length.
- **Idempotence**: `f(f(x)) == f(x)`.

Input generation is type-directed: the system reads parameter annotations to produce appropriate random values (integers, floats, strings, lists, dicts, tuples, booleans).

**Source 4: Pattern Retrieval** (`property_inference/pattern_retrieval.py`)

Matches the function name and source text against a curated library of common algorithm patterns. Supported patterns include: `sort`, `max`, `min`, `sum`, `average`, `reverse`, `unique`, and `filter`. Each pattern maps to a set of pre-defined postconditions.

**Source 5: LLM Extraction** (`property_inference/llm_extractor.py`)

Sends the function source, signature, docstring, and module context to a large language model (GPT-4 via OpenAI or CodeLlama via Ollama) with a structured prompt requesting JSON output of preconditions, postconditions, invariants, and example I/O pairs. The LLM response is parsed and converted into `Property` objects. This source is optional and gracefully degrades if no LLM backend is configured.

**Property Fusion** (`property_inference/fusion.py`)

The five `PropertySet` outputs are merged using the following procedure:

1. Properties are grouped by `(kind, description[:80])` to identify semantically equivalent properties from different sources.
2. For each group, the average confidence is computed and the set of contributing sources is recorded.
3. A property is retained if:
   - Its average confidence meets the threshold (default: 0.5) **and** it has support from at least 2 sources, **or**
   - Its average confidence exceeds 0.7 (high-confidence override), **or**
   - Its average confidence exceeds 1.3x the threshold (moderate-confidence single-source).
4. Retained properties receive a corroboration bonus: `confidence *= (1 + 0.1 * n_sources)`.
5. Conflicting postconditions (e.g., "sorted ascending" vs. "sorted descending", "maximum" vs. "minimum") are resolved by retaining the higher-confidence property.

### Phase 2: Bug Detection

Three complementary detection strategies search for concrete inputs that violate inferred properties.

**Strategy 1: Property-Based Testing** (`detection/hypothesis_tester.py`)

For each postcondition with a Python predicate, the system generates up to 200 inputs (configurable via `hypothesis_max_examples`) using Hypothesis-derived strategies that respect parameter type annotations. Each input is checked against all preconditions (inputs violating preconditions are skipped), then the function is executed and the output is tested against the postcondition. Violations are recorded as `(args, kwargs, violated_property)` triples.

Example I/O pairs from the property set are also tested.

**Strategy 2: Symbolic Execution** (`detection/symbolic_executor.py`)

For functions whose parameters are exclusively numeric (`int` or `float`), the system constructs Z3 symbolic variables and attempts to find concrete counterexamples for each postcondition that provides a Z3 predicate. When Z3 reports SAT, the model is extracted as concrete input values, the function is executed on those values, and the postcondition is re-checked in Python to confirm the violation.

The solver timeout is configurable (default: 30 seconds).

**Strategy 3: Outlier Detection** (`detection/outlier_detector.py`)

The function is executed on 300 randomly generated inputs. For numeric outputs, z-scores are computed; outputs exceeding 3.0 standard deviations from the mean are flagged as outliers. For string outputs, an analogous length-based z-score analysis is applied.

**False Positive Filtering** (`detection/reflection.py`)

All detected failures are re-executed to confirm the violation persists. This eliminates transient failures caused by non-determinism or environmental factors.

### Phase 3: Execution Tracing

For every passing and failing input (up to 50 passing and 20 failing), the target function is re-executed under `sys.settrace` instrumentation.

The `TraceCollector` (`tracing/tracer.py`) records, for each executed line:

- Line number (adjusted relative to the function's start line).
- All local variables and their values, summarized as `VariableSnapshot` objects with type, value, and statistical summaries (min, max, length, sample elements for collections).
- Loop iteration count (incremented when the same line executes consecutively).
- Call depth.

Each execution produces an `ExecutionTrace` containing the full event sequence, input arguments, output value, pass/fail status, exception text (if any), and wall-clock duration in nanoseconds.

### Phase 4: Fault Localization

The localization subsystem combines three orthogonal signals to rank each source line by suspiciousness.

**Signal 1: Spectrum-Based Fault Localization (SBFL)** (`localization/sbfl.py`)

Computes three standard SBFL metrics from line-level coverage data:

- **Tarantula**: `(ef / (ef + nf)) / ((ef / (ef + nf)) + (ep / (ep + np)))`
- **Ochiai**: `ef / sqrt((ef + ep) * (ef + nf))`
- **DStar** (D* with exponent 2): `ef^2 / (ep + nf)`

where `ef` = executed in failing, `ep` = executed in passing, `nf` = not executed in failing, `np` = not executed in passing. The three metrics are averaged and normalized to [0, 1].

**Signal 2: KL-Divergence Analysis** (`localization/divergence.py`)

For each line and each variable observed at that line, the system computes the Kullback-Leibler divergence between the distribution of that variable's values in passing traces versus failing traces. Distributions are estimated via 10-bin histograms with Laplace smoothing (epsilon = 1e-10). The maximum divergence across all variables at a given line becomes that line's divergence score. Scores are normalized to [0, 1].

**Weighted Fusion** (`localization/ranker.py`)

The two signals are combined with configurable weights (defaults: SBFL 0.6, divergence 0.4):

```
total_score = w_sbfl * sbfl_combined + w_div * divergence
```

Lines are sorted by total score in descending order and the top-K (default: 5) are returned as `SuspiciousLocation` objects.

### Phase 5: Patch Synthesis

The synthesis subsystem generates candidate patches using a three-tier escalation strategy. Each tier has a configurable budget (default: `[5, 5, 3]` patches per tier).

**Tier 1: Template-Based Fixes** (`synthesis/template_fixer.py`)

Applies eleven parameterized repair templates to each suspicious line:

| Template | Transformation |
|----------|---------------|
| `off_by_one_range` | `range(n)` to `range(n - 1)` or `range(len(x))` |
| `off_by_one_range_start` | `range(1, len(x))` to `range(len(x))` |
| `operator_swap` | `<=` to `<`, `>=` to `>`, `==` to `!=` |
| `comparison_swap` | `>` to `<` and vice versa (for min/max confusion) |
| `missing_increment` | (structural check for missing accumulation) |
| `comparison_order` | `if 5 < x` to `if x > 5` |
| `premature_return` | Comments out `else: return ...` patterns |
| `bad_initializer` | `result = 0` to `result = float('-inf')`, `total = 1` to `total = 0` |
| `sort_mutation` | `return a.sort()` to `return sorted(a)` |
| `swapped_min_max` | `return max(a), min(a)` to `return min(a), max(a)` |

Context-level templates also detect:
- **Missing return**: inserts `return None` in functions without return statements.
- **Wrong accumulator**: replaces `+= 1` with `+= loop_var` (count vs. sum) or `+= len(a)` with `+= loop_var`.
- **Missing denominator guard**: inserts `if denom == 0: return float('inf')` before division.
- **String join separator**: replaces hardcoded `","` with the `sep` parameter.

**Tier 2: Z3 Constraint Synthesis** (`synthesis/constraint_solver.py`)

For each suspicious line, the system:

1. Collects variable snapshots at that line from both passing and failing traces.
2. Enumerates candidate expressions over local variables (`v`, `v + 1`, `v - 1`, `len(v)`, `min(v1, v2)`, `max(v1, v2)`, `abs(v)`, constants).
3. For each candidate, checks whether it matches all passing snapshots and differs from at least one failing snapshot.
4. If enumeration fails, falls back to Z3 template solving: parameterized expressions of the form `v + c`, `v - c`, `c - v`, `v * c` where `c` is a symbolic constant constrained by passing I/O.

Successful expressions are substituted into the suspicious line's assignment or return statement.

**Tier 3: LLM-Guided Repair** (`synthesis/llm_agent.py`)

Constructs a detailed prompt containing:

- The function source code.
- Ranked suspicious locations with scores.
- Inferred properties with confidence values.
- Up to 3 passing and 5 failing input-output examples.

The prompt is sent to the configured LLM backend with a system instruction emphasizing minimal changes, regression preservation, and fix correctness. The response is parsed to extract a Python code block containing the repaired function.

**Deduplication.** All candidate patches across tiers are deduplicated by the first 200 characters of `patched_source` before validation.

### Phase 6: Validation

Every candidate patch undergoes a two-stage validation process.

**Stage 1: Compilation.** The patched source is compiled and the repaired function is extracted by scanning the resulting namespace for callable objects.

**Stage 2: Regression Testing** (`validation/regression.py`). For each previously passing input, both the original and patched functions are executed. A regression is flagged if:

- The output types differ.
- For numeric outputs, the absolute difference exceeds 1e-9.
- For other types, the string representations differ.

**Stage 3: Fix Verification.** For each previously failing input, the patched function is executed and all postconditions are re-checked. An input is considered fixed if all postconditions are satisfied.

The validation score is computed as:

```
score = 1.0 - 0.3 * min(1, regressions / n_passing) - 0.5 * min(1, remaining_failures / n_failing)
```

A patch passes validation if `score >= 0.3`, there are zero regressions, and at least one failure is fixed.

**Patch Ranking** (`validation/ranker.py`). Validated patches are scored by a weighted combination:

```
final_score = 0.5 * behavioral_score + 0.3 * ast_similarity + 0.2 * (1 / (1 + tier))
```

where `ast_similarity` is the `SequenceMatcher` ratio between the AST dumps of the original and patched source. This biases toward minimal, low-tier (simpler) fixes.

---

## Installation

**Requirements:** Python 3.10 or later.

### From source

```bash
git clone https://github.com/your-org/silentfix.git
cd silentfix
pip install -e .
```

### With development dependencies

```bash
pip install -e ".[dev]"
```

Development extras include `pytest`, `pytest-cov`, `mypy`, `ruff`, and `black`.

### Dependencies

| Package | Minimum Version | Role |
|---------|----------------|------|
| `z3-solver` | 4.12.0 | Symbolic execution, constraint-based synthesis |
| `hypothesis` | 6.80.0 | Property-based test input generation |
| `openai` | 1.0.0 | OpenAI API client (LLM repair, property extraction) |
| `httpx` | 0.24.0 | HTTP client for Ollama backend |
| `click` | 8.0.0 | CLI framework |
| `rich` | 13.0.0 | Terminal output formatting |

---

## Usage

### Python API

**Minimal example:**

```python
from silentfix import fix_function

def buggy_max(a: list[int]) -> int:
    result = 0
    for x in a:
        if x > result:
            result = x
    return result

result = fix_function(buggy_max)

if result.success:
    print(f"Repaired in {result.iterations} iteration(s), tier {result.patches[0].tier}")
    print(result.patches[0].patched_source)
```

**File-level repair:**

```python
from silentfix.main import fix_file

# Target a specific function
result = fix_file("path/to/module.py", func_name="compute_average")

# Auto-detect the first public function
result = fix_file("path/to/module.py")
```

**Engine with custom configuration:**

```python
from silentfix.core.engine import SilentFixPro
from silentfix.core.types import Config

config = Config(
    max_iterations=3,
    hypothesis_max_examples=100,
    top_k_suspicious=3,
    sbfl_weight=0.5,
    divergence_weight=0.3,
    neural_weight=0.2,
)

engine = SilentFixPro(config=config)
result = engine.fix(target_function)
```

**Inspecting intermediate results:**

```python
result = fix_function(target)

# Inferred properties
for prop in result.properties.all():
    print(f"  [{prop.kind.value}] {prop.description} (conf={prop.confidence:.2f}, src={prop.source})")

# Bug-triggering inputs
for args, kwargs in result.failing_inputs:
    print(f"  f{args} -> {target(*args)}")

# Fault localization ranking
for loc in result.suspicious_locations:
    print(f"  Line {loc.line_no}: total={loc.total_score:.3f} "
          f"(sbfl={loc.sbfl_score:.3f}, div={loc.divergence_score:.3f})")
```

### Command-Line Interface

SilentFix registers a `silentfix` entry point via `pyproject.toml`.

**Full repair pipeline:**

```bash
# Repair a named function
silentfix fix path/to/module.py:function_name

# Auto-detect and repair the first public function
silentfix fix path/to/module.py
```

Output includes repair status, iteration count, patch diff with tier, a table of suspicious locations with SBFL and divergence scores, and a summary of inferred properties.

**Analysis only (no repair):**

```bash
silentfix analyze path/to/module.py
silentfix analyze path/to/module.py function_name
```

Output includes property count, number of bug-triggering inputs discovered, and number of suspicious locations.

---

## Configuration

All parameters are set via the `Config` dataclass or the `set_config` / `get_config` convenience functions.

```python
from silentfix.config import set_config, get_config

set_config(max_iterations=10, hypothesis_max_examples=500)
cfg = get_config()
```

### Parameter Reference

**LLM Backend**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `llm_backend` | `"openai"` | Backend selection: `"openai"`, `"ollama"`, or `"mock"` |
| `llm_model` | `"gpt-4"` | Model identifier for completions |
| `openai_api_key` | `""` | OpenAI API key (or set `OPENAI_API_KEY` env var) |
| `openai_model` | `"gpt-4"` | Model for OpenAI backend |
| `ollama_url` | `"http://localhost:11434"` | Ollama server endpoint |
| `ollama_model` | `"codellama"` | Model for Ollama backend |

**Property Inference**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `property_confidence_threshold` | `0.5` | Minimum average confidence to retain a property |
| `min_supporting_sources` | `2` | Minimum distinct sources required for corroboration |
| `dynamic_miner_samples` | `200` | Number of random inputs for dynamic invariant mining |

**Detection**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `hypothesis_max_examples` | `200` | Maximum inputs generated per postcondition test |
| `symbolic_timeout_s` | `30` | Z3 solver timeout in seconds |

**Localization**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `top_k_suspicious` | `5` | Number of top-ranked suspicious lines to return |
| `sbfl_weight` | `0.6` | Weight of SBFL signal in composite ranking |
| `divergence_weight` | `0.4` | Weight of KL-divergence signal in composite ranking |

**Synthesis and Validation**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_iterations` | `5` | Maximum repair attempts before termination |
| `patch_budget_tiers` | `[5, 5, 3]` | Maximum candidate patches per tier |
| `held_out_ratio` | `0.2` | Fraction of inputs reserved for held-out validation |

---

## LLM Backend Setup

LLMs are used in two optional components: property extraction (Phase 1, Source 5) and LLM-guided repair (Phase 5, Tier 4). SilentFix functions without any LLM backend — Tiers 1-2 (template fixes and Z3 constraint synthesis) operate independently.

**OpenAI**

```bash
export OPENAI_API_KEY="sk-..."
```

```python
from silentfix.config import set_config
set_config(llm_backend="openai", openai_model="gpt-4")
```

**Ollama (local inference)**

```bash
ollama serve
ollama pull codellama
```

```python
from silentfix.config import set_config
set_config(llm_backend="ollama", ollama_url="http://localhost:11434", ollama_model="codellama")
```

**Disable LLMs**

```python
from silentfix.config import set_config
set_config(llm_backend="mock")
```

---

## Evaluation

SilentFix includes a benchmark suite of 15 hand-crafted silent-bug cases covering common Python logic error patterns.

### Running the benchmark

```bash
python -m benchmark.runner
```

### Benchmark cases

| ID | Pattern | Description |
|----|---------|-------------|
| 1 | Bad initializer | `max()` initialized to `0`; fails on all-negative lists |
| 2 | Off-by-one range | `sum()` loop starts at index 1, omitting the first element |
| 3 | Wrong initial value | `sum()` initialized to `1` instead of `0` |
| 4 | Wrong operator | `min()` uses `>` instead of `<` |
| 5 | Wrong accumulator | Loop body adds `len(a)` instead of element value |
| 6 | Boundary condition | Uses `<` instead of `<=` for inclusive range check |
| 7 | Mutation return | `a.sort()` returns `None`; should use `sorted(a)` |
| 8 | Missing guard | Access `a[0]` without empty-list guard |
| 9 | Count vs. sum | Increments by `1` instead of by element value |
| 10 | Boolean connective | Uses `and` instead of `or` for disjunctive range check |
| 11 | Variable shadowing | Inner loop variable shadows outer loop variable |
| 12 | Swapped branches | `True`/`False` returned in wrong branches |
| 13 | Missing zero check | Division without zero-denominator guard |
| 14 | Swapped outputs | Returns `(max, min)` instead of `(min, max)` |
| 15 | Wrong separator | Hardcodes `","` instead of using the `sep` parameter |

### Results

| Metric | Count |
|--------|-------|
| Total cases | 15 |
| Bugs detected (violation-triggering inputs found) | 10 |
| Bugs auto-repaired (patch generated and validated) | 7 |

Detection coverage is primarily limited by the property inference subsystem's ability to derive sufficiently precise postconditions for complex behavioral patterns (cases 6, 8, 10, 11, 12). Repair success depends on the faulty expression falling within the search space of Tiers 1-2; cases 7 (sort mutation), 13 (missing zero guard), and 14 (swapped min/max) are detected but not yet auto-repaired due to validation regressions or template-scope limitations.

---

## Project Structure

```
silentfix/
    __init__.py                          Public API exports
    config.py                            Global configuration management
    main.py                              CLI entry point, fix_function, fix_file

    core/
        engine.py                        SilentFixPro orchestrator
        types.py                         Property, PropertySet, Patch, RepairResult,
                                         ExecutionTrace, SuspiciousLocation, Config
        utils.py                         AST utilities, safe eval, function cloning

    property_inference/
        static_extractor.py              Name, type hint, docstring, comment analysis
        type_inferrer.py                 Return annotation-based property generation
        dynamic_miner.py                 Random-execution invariant mining
        pattern_retrieval.py             Curated algorithm pattern matching
        llm_extractor.py                 LLM-based property extraction
        fusion.py                        Multi-source confidence-weighted fusion

    detection/
        hypothesis_tester.py             Property-based testing via Hypothesis
        symbolic_executor.py             Z3-based symbolic counterexample search
        outlier_detector.py              Statistical z-score outlier flagging
        reflection.py                    False positive re-execution filter

    tracing/
        tracer.py                        sys.settrace instrumentation and collection

    localization/
        sbfl.py                          Tarantula, Ochiai, DStar computation
        divergence.py                    KL-divergence variable distribution analysis
        ranker.py                        Weighted signal fusion and top-K ranking

    synthesis/
        synthesizer.py                   Three-tier patch generation orchestrator
        template_fixer.py                Eleven parameterized repair templates
        constraint_solver.py             Z3-based expression synthesis
        llm_agent.py                     LLM-guided function repair

    validation/
        regression.py                    Regression testing and fix verification
        ranker.py                        AST-similarity-weighted patch ranking

    llm/
        client.py                        Unified LLM client (OpenAI, Ollama, mock)
        prompts.py                       System prompts for extraction and repair

benchmark/
    runner.py                            Benchmark execution harness
    cases/
        simple_bugs.py                   15 silent-bug benchmark cases

tests/
    test_property_inference.py           Property extraction unit tests
    test_synthesis.py                    Patch synthesis unit tests
    test_integration.py                  End-to-end pipeline tests
    test_benchmark.py                    Benchmark validation tests
```

---

## Data Types and API Reference

### `RepairResult`

Primary return type from `fix_function()` and `SilentFixPro.fix()`.

```python
@dataclass
class RepairResult:
    success: bool                                   # True if a validated patch was found
    original_source: str                            # Original function source code
    patched_source: str | None                      # Patched source (None if repair failed)
    patches: list[Patch]                            # All validated patches, ranked
    properties: PropertySet | None                  # Inferred behavioral specification
    failing_inputs: list[tuple]                     # Inputs that violated properties
    suspicious_locations: list[SuspiciousLocation]  # Ranked fault locations
    iterations: int                                 # Number of repair iterations executed
    error: str | None                               # Error description (if repair failed)
```

### `Patch`

```python
@dataclass
class Patch:
    diff: str               # Patch diff or full patched source
    patched_source: str     # Complete repaired function source
    tier: int               # Synthesis tier (1: template, 2: Z3, 3: neural, 4: LLM)
    score: float            # Composite quality score in [0, 1]
    verified: bool          # True if formally verified via Z3
    description: str        # Human-readable fix description
```

### `SuspiciousLocation`

```python
@dataclass
class SuspiciousLocation:
    line_no: int            # Source line number (1-indexed, relative to function)
    node_type: str          # AST node type at this line
    sbfl_score: float       # SBFL suspiciousness score in [0, 1]
    neural_score: float     # GNN suspiciousness score in [0, 1]
    divergence_score: float # KL-divergence score in [0, 1]
    total_score: float      # Weighted composite score
    context: str            # Source text at this line
```

### `PropertySet`

```python
@dataclass
class PropertySet:
    preconditions: list[Property]                      # Input constraints
    postconditions: list[Property]                     # Output constraints
    invariants: list[Property]                         # Loop/state invariants
    metamorphic: list[Property]                        # Metamorphic relations
    examples: list[tuple[tuple, dict, Any]]            # Known I/O pairs (args, kwargs, expected)
```

### `Property`

```python
@dataclass
class Property:
    kind: PropertyKind                  # pre, post, invariant, metamorphic
    predicate_py: Callable | None       # Python predicate: (input_dict, output) -> bool
    predicate_z3: Callable | None       # Z3 predicate: (z3_vars) -> z3.BoolRef
    description: str                    # Human-readable description
    confidence: float                   # Confidence score in [0, 1]
    source: str                         # Provenance: function_name, type_hint, dynamic_mining, etc.
```

### `ExecutionTrace`

```python
@dataclass
class ExecutionTrace:
    input_args: tuple                   # Function call arguments
    input_kwargs: dict                  # Function call keyword arguments
    output: Any | None                  # Return value
    events: list[TraceEvent]            # Line-level execution events
    passed: bool                        # True if no exception was raised
    exception: str | None               # Exception text (if raised)
    duration_ns: int                    # Wall-clock duration in nanoseconds
```

---

## Testing

### Run the test suite

```bash
pytest tests/ -v
```

### Test modules

| Module | Scope |
|--------|-------|
| `test_property_inference.py` | Static extraction, name-based heuristics, type-based properties |
| `test_synthesis.py` | Template fix generation, constraint solver, patch construction |
| `test_integration.py` | End-to-end repair pipeline on `max`, `sum`, `contains`, `average` bugs |
| `test_benchmark.py` | Benchmark case loading and validation |

### Multi-version testing

```bash
tox
```

Runs across Python 3.10, 3.11, and 3.12 as defined in `tox.ini`.

### Continuous integration

GitHub Actions runs `pytest tests/ -v --timeout=120` on every push and pull request to `main`, across Python 3.10, 3.11, and 3.12. See `.github/workflows/tests.yml`.

---

## Contributing

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/description`.
3. Install development dependencies: `pip install -e ".[dev]"`.
4. Run tests before submitting: `pytest tests/ -v`.
5. Run linting: `ruff check silentfix/` and `black --check silentfix/`.
6. Submit a pull request with a clear description of changes.

**Code standards:** Black formatter (line length 100), Ruff linter, mypy strict type checking, pytest with Hypothesis for property-based tests.

---

## License

MIT. See [LICENSE](LICENSE) for the full text.

---

## References

- Le Goues, C., Pradel, M., & Roychoudhury, A. (2019). Automated program repair. *Communications of the ACM*, 62(12), 56-65.
- Papadakis, M., et al. (2019). Mutation testing advances: An analysis and survey. *Advances in Computers*, 112, 275-378.
- Jones, J. A., Harrold, M. J., & Stasko, J. (2002). Visualization of test information to assist fault localization. *ICSE 2002*.
- Abreu, R., Zoeteweij, P., & Van Gemund, A. J. (2007). On the accuracy of spectrum-based fault localization. *TAAS*, 2(3).
- Wong, W. E., et al. (2016). A survey on software fault localization. *IEEE TSE*, 42(8), 707-740.
- Schlichtkrull, M., et al. (2018). Modeling relational data with graph convolutional networks. *ESWC 2018*.
