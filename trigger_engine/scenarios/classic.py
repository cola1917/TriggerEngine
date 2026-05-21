from __future__ import annotations

from trigger_engine.engine.registry import RuleRegistry
from trigger_engine.operators.builtins import register_builtin_operators
from trigger_engine.operators.registry import OperatorRegistry


CLASSIC_SCENARIO_RULES_YAML = """
rules:
  # --- Stopped Vehicle ---
  - id: vehicle_stopped
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
        - operator: predicate.speed_below
          args:
            threshold_mps: 0.5
    emit:
      tag: vehicle_stopped

  - id: vehicle_stopped_for_3_frames
    kind: temporal
    subject: agent
    when:
      tag: vehicle_stopped
      sustained:
        frames: 3
    emit:
      tag: vehicle_stopped_for_3_frames

  # --- Low TTC ---
  - id: low_ttc_pair
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.pair_types_are
          args:
            ego_type: vehicle
            other_type: vehicle
        - operator: predicate.pair_in_front
          args:
            min_longitudinal_m: 0.0
            max_lateral_m: 4.0
        - operator: predicate.low_ttc
          args:
            threshold_s: 3.0
            max_lateral_m: 4.0
    emit:
      tag: low_ttc_pair

  - id: persistent_low_ttc_pair
    kind: temporal
    subject: agent_pair
    when:
      tag: low_ttc_pair
      sustained:
        frames: 3
    emit:
      tag: persistent_low_ttc_pair

  # --- Cut-in Candidate (sustained) ---
  - id: cut_in_candidate
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.pair_types_are
          args:
            ego_type: vehicle
            other_type: vehicle
        - operator: predicate.close_lateral_gap
          args:
            max_lateral_m: 3.0
            max_longitudinal_m: 10.0
        - operator: predicate.lateral_motion_toward
          args:
            min_lateral_speed_mps: 0.2
        - operator: predicate.heading_converging
          args:
            min_heading_delta_rad: 0.05
            max_heading_delta_rad: 0.5
    emit:
      tag: cut_in_candidate

  - id: cut_in_developing
    kind: temporal
    subject: agent_pair
    when:
      tag: cut_in_candidate
      sustained:
        frames: 3
    emit:
      tag: cut_in_developing

  # --- Cut-in Sequence ---
  - id: adjacent_vehicle
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.pair_types_are
          args:
            ego_type: vehicle
            other_type: vehicle
        - operator: predicate.lateral_gap_between
          args:
            min_lateral_m: 1.5
            max_lateral_m: 4.5
            max_longitudinal_m: 15.0
    emit:
      tag: adjacent_vehicle

  - id: cut_in_lateral_approach
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.pair_types_are
          args:
            ego_type: vehicle
            other_type: vehicle
        - operator: predicate.lateral_gap_between
          args:
            min_lateral_m: 1.0
            max_lateral_m: 4.5
            max_longitudinal_m: 15.0
        - operator: predicate.lateral_motion_toward
          args:
            min_lateral_speed_mps: 0.2
    emit:
      tag: cut_in_lateral_approach

  - id: same_path_overlap
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.pair_types_are
          args:
            ego_type: vehicle
            other_type: vehicle
        - operator: predicate.same_path_overlap
          args:
            max_lateral_m: 1.2
            min_longitudinal_m: 0.0
            max_longitudinal_m: 20.0
    emit:
      tag: same_path_overlap

  - id: cut_in_confirmed
    kind: temporal
    subject: agent_pair
    when:
      sequence:
        - tag: adjacent_vehicle
        - tag: cut_in_lateral_approach
        - tag: same_path_overlap
      within_frames: 8
    emit:
      tag: cut_in_confirmed

  - id: cut_in_risk
    kind: temporal
    subject: agent_pair
    when:
      sequence:
        - tag: adjacent_vehicle
        - tag: cut_in_lateral_approach
        - tag: same_path_overlap
        - tag: low_ttc_pair
      within_frames: 8
    emit:
      tag: cut_in_risk

  # --- Traffic Light Interaction ---
  - id: vehicle_stopped_at_red
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
        - operator: predicate.speed_below
          args:
            threshold_mps: 0.5
        - operator: predicate.near_red_light_stop_point
          args:
            max_distance_m: 5.0
    emit:
      tag: vehicle_stopped_at_red

  - id: vehicle_still_stopped_at_red
    kind: temporal
    subject: agent
    when:
      tag: vehicle_stopped_at_red
      sustained:
        frames: 3
    emit:
      tag: vehicle_still_stopped_at_red

  # --- Red Light Running (map-aware) ---
  - id: red_light_stop_line_approach
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
        - operator: predicate.red_light_before_stop_line
          args:
            max_lateral_m: 2.0
            max_before_stop_line_m: 12.0
            min_speed_mps: 0.5
            max_heading_delta_rad: 0.7
    emit:
      tag: red_light_stop_line_approach

  - id: red_light_stop_line_crossed
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
        - operator: predicate.red_light_after_stop_line
          args:
            max_lateral_m: 2.0
            min_after_stop_line_m: 0.5
            max_after_stop_line_m: 15.0
            min_speed_mps: 0.5
            max_heading_delta_rad: 0.7
    emit:
      tag: red_light_stop_line_crossed

  - id: red_light_running
    kind: temporal
    subject: agent
    when:
      sequence:
        - tag: red_light_stop_line_approach
        - tag: red_light_stop_line_crossed
      within_frames: 5
    emit:
      tag: red_light_running
"""


def register_classic_scenario_pack(
    operator_registry: OperatorRegistry,
    rule_registry: RuleRegistry,
    plan_id: str = "classic_v1",
):
    register_builtin_operators(operator_registry)
    plan = rule_registry.register_yaml(plan_id, CLASSIC_SCENARIO_RULES_YAML)
    rule_registry.activate(plan_id)
    return plan
