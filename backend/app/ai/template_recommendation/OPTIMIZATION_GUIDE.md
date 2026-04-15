# Template Recommendation Optimization Guide

## Scope
This document summarizes practical backend optimization ideas for the template recommendation flow with teacher/student scenarios as first-class concerns.

## Already Implemented in This Change
- Added Chinese-friendly intent keyword detection with typo-tolerant normalization.
- Added persona presets in schema:
  - student_individual
  - student_team_project
  - teaching_class_service
- Added per-preset resource baselines so teachers do not need to guess CPU/RAM/Disk from scratch.

## Recommended Next Steps

### 1) Single Source of Truth for Resource Floors
Problem:
- VM/LXC disk floor values are still distributed across modules.

Recommendation:
- Create one policy module for floor values and defaults.
- All places (intent normalization, form prefill, availability, and provisioning) should read from that module.

Suggested policy defaults:
- VM minimum disk: 20 GB
- LXC minimum disk: 8 GB

### 2) Request Validation by Resource Type
Problem:
- Validation currently allows broad ranges and relies on fallback logic later.

Recommendation:
- Add conditional schema validation:
  - VM requires template_id, username, disk_size >= 20
  - LXC requires ostemplate, rootfs_size >= 8
- Return explicit and user-friendly validation messages.

### 3) Better zh-TW Intent Robustness
Problem:
- Student inputs often include mixed language, abbreviations, and colloquial words.

Recommendation:
- Expand keyword dictionary with classroom vocabulary and common typo forms.
- Add context cues:
  - "期末專題", "課堂展示", "多人同時上線", "作業繳交"
- Add weak-signal voting instead of single keyword hit.

### 4) Teacher-Focused Explainability
Problem:
- Teachers reviewing requests need quick, auditable reasoning.

Recommendation:
- Return a compact decision_trace section:
  - matched_intent_flags
  - selected_preset
  - why_vm_or_lxc
  - resource_floor_applied
  - top_capacity_constraints

### 5) Preset-Aware Capacity Guardrails
Problem:
- Presets help planning but capacity pressure still varies by schedule.

Recommendation:
- Add policy overlays by preset:
  - student_individual: prioritize low cost
  - student_team_project: prioritize moderate redundancy
  - teaching_class_service: prioritize stability and predictable latency

### 6) Telemetry and Continuous Tuning
Problem:
- Hard to know if recommendations are actually effective.

Recommendation:
- Track:
  - recommendation acceptance rate
  - post-provision 24h/72h CPU/MEM/DISK pressure
  - request revision count before approval
  - over/under-provision incidents

### 7) API Contract Enhancements
Recommendation:
- Include in response persona section:
  - preset
  - resource_baseline
- Keep this stable so frontend can display preset cards and rationale.

## Suggested Teacher/Student Preset Interpretation
- student_individual:
  - focus on minimal workable resources and fast provisioning.
- student_team_project:
  - allow moderate headroom for collaboration and demos.
- teaching_class_service:
  - prioritize stability for concurrent student access.

## Rollout Plan
1. Merge current intent and preset changes.
2. Add conditional schema validation for VM/LXC request shapes.
3. Add decision_trace response block for reviewer transparency.
4. Add telemetry dashboard for recommendation outcomes.
5. Re-tune thresholds monthly based on real usage.
