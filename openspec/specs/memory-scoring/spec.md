# Memory Scoring Specification

## Purpose

Define the importance scoring mechanism using a local Llama 3.2 1B model, relying on robust regex extraction instead of strict JSON formatting.

## Requirements

### Requirement: Prompt-Based Evaluation

The scoring module MUST prompt the local Llama model to evaluate an episode and append a specific score string.

#### Scenario: Generate score prompt
- **Given** an `Episode` containing a problem, process, and solution
- **When** `scoring.evaluate_importance(episode)` is called
- **Then** the prompt MUST instruct the model to analyze the episode's significance
- **And** the prompt MUST explicitly demand the response ends with the exact format `SCORE: X.X` where X.X is between 0.0 and 1.0.

### Requirement: Regex Score Extraction

The module MUST NOT rely on JSON parsing for the model's output, given the limitations of 1B parameters.

#### Scenario: Extract valid score
- **Given** the model outputs text like "This episode is crucial because... SCORE: 0.8"
- **When** parsing the response
- **Then** the system MUST use a regular expression to extract `0.8`
- **And** the extracted value MUST be parsed as a float.

### Requirement: Fallback Mechanism

The scoring module MUST handle parsing failures gracefully without throwing exceptions.

#### Scenario: Handle malformed output
- **Given** the model outputs text lacking the `SCORE: X.X` format or containing an invalid number
- **When** the regex fails to find a valid score
- **Then** the system MUST log a warning
- **And** it MUST return a default fallback score (e.g., 0.5).
