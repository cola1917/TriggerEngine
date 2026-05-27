from __future__ import annotations

from trigger_engine.engine.registry import RuleRegistry
from trigger_engine.operators.builtins import register_builtin_operators
from trigger_engine.operators.registry import OperatorRegistry


CLASSIC_SCENARIO_RULES_YAML = """
rules:
  # --- Stopped Vehicle (SDC) ---
  - id: sdc_vehicle_stopped
    kind: single_frame
    subject: sdc_agent
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
        - operator: predicate.speed_below
          args:
            threshold_mps: 0.5
    emit:
      tag: sdc_vehicle_stopped
      intent: debug
      policy:
        compact:
          by: subject
          mode: interval

  - id: sdc_vehicle_stopped_for_3_frames
    kind: temporal
    subject: sdc_agent
    when:
      tag: sdc_vehicle_stopped
      sustained:
        frames: 3
    emit:
      tag: sdc_vehicle_stopped_for_3_frames
      intent: debug

  # --- Low TTC ---
  - id: low_ttc_pair
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.pair_types_are
          args:
            ego_type: vehicle
            other_type: vehicle
        - operator: predicate.pair_ego_speed_above
          args:
            threshold_mps: 0.5
        - operator: predicate.same_lane_or_path
          args:
            max_lane_lateral_m: 1.8
            max_heading_delta_rad: 0.7
            fallback_max_lateral_m: 1.2
            fallback_max_heading_delta_rad: 0.35
            allow_fallback_without_map: true
        - operator: predicate.pair_in_front
          args:
            min_longitudinal_m: 1.0
            max_lateral_m: 2.0
        - operator: predicate.low_ttc
          args:
            threshold_s: 3.0
            max_lateral_m: 2.0
            min_closing_speed_mps: 1.0
    emit:
      tag: low_ttc_pair
      intent: supporting

  - id: persistent_low_ttc_pair
    kind: temporal
    subject: sdc_pair
    when:
      tag: low_ttc_pair
      sustained:
        frames: 3
    emit:
      tag: persistent_low_ttc_pair
      intent: review
      policy:
        episode:
          by: subject
          mode: interval

  # --- Cut-in Candidate (sustained) ---
  - id: cut_in_candidate
    kind: single_frame
    subject: sdc_pair
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
      intent: debug

  - id: cut_in_developing
    kind: temporal
    subject: sdc_pair
    when:
      tag: cut_in_candidate
      sustained:
        frames: 3
    emit:
      tag: cut_in_developing
      intent: debug

  # --- Cut-in Sequence ---
  - id: adjacent_vehicle
    kind: single_frame
    subject: sdc_pair
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
      intent: supporting
      policy:
        compact:
          by: subject
          mode: interval

  - id: cut_in_lateral_approach
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.pair_types_are
          args:
            ego_type: vehicle
            other_type: vehicle
        - operator: predicate.pair_ego_speed_above
          args:
            threshold_mps: 0.5
        - operator: predicate.pair_other_speed_above
          args:
            threshold_mps: 0.5
        - operator: predicate.lateral_gap_between
          args:
            min_lateral_m: 1.0
            max_lateral_m: 4.5
            max_longitudinal_m: 15.0
        - operator: predicate.lateral_motion_toward
          args:
            min_lateral_speed_mps: 0.2
        - operator: predicate.heading_converging
          args:
            min_heading_delta_rad: 0.0
            max_heading_delta_rad: 0.7
    emit:
      tag: cut_in_lateral_approach
      intent: supporting
      policy:
        compact:
          by: subject
          mode: interval

  - id: same_path_overlap
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.pair_types_are
          args:
            ego_type: vehicle
            other_type: vehicle
        - operator: predicate.pair_ego_speed_above
          args:
            threshold_mps: 0.5
        - operator: predicate.same_path_overlap
          args:
            max_lateral_m: 1.2
            min_longitudinal_m: 0.0
            max_longitudinal_m: 20.0
    emit:
      tag: same_path_overlap
      intent: supporting
      policy:
        compact:
          by: subject
          mode: interval

  - id: cut_in_confirmed
    kind: temporal
    subject: sdc_pair
    when:
      sequence:
        - tag: adjacent_vehicle
        - tag: cut_in_lateral_approach
        - tag: same_path_overlap
      within_frames: 8
    emit:
      tag: cut_in_confirmed
      intent: review
      metadata:
        review_family: cut_in
        review_priority: 10
      policy:
        episode:
          by: subject
          mode: interval

  - id: cut_in_risk
    kind: temporal
    subject: sdc_pair
    when:
      sequence:
        - tag: adjacent_vehicle
        - tag: cut_in_lateral_approach
        - tag: same_path_overlap
        - tag: low_ttc_pair
      within_frames: 8
    emit:
      tag: cut_in_risk
      intent: review
      metadata:
        review_family: cut_in
        review_priority: 20
      policy:
        episode:
          by: subject
          mode: interval

  # --- Traffic Light Interaction (SDC) ---
  - id: sdc_vehicle_stopped_at_red
    kind: single_frame
    subject: sdc_agent
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
      tag: sdc_vehicle_stopped_at_red
      intent: debug
      policy:
        compact:
          by: subject
          mode: interval

  - id: sdc_vehicle_still_stopped_at_red
    kind: temporal
    subject: sdc_agent
    when:
      tag: sdc_vehicle_stopped_at_red
      sustained:
        frames: 3
    emit:
      tag: sdc_vehicle_still_stopped_at_red
      intent: debug

  # --- Red Light Running (map-aware, same-lane crossing) ---
  - id: red_light_stop_line_approach
    kind: single_frame
    subject: sdc_agent
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
      intent: supporting

  - id: red_light_stop_line_crossed
    kind: single_frame
    subject: sdc_agent
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
            max_lane_heading_change_rad: 0.35
            lane_heading_lookahead_m: 15.0
            max_future_heading_change_rad: 0.25
            future_heading_horizon_seconds: 2.0
            extended_max_future_heading_change_rad: 0.45
            extended_future_heading_horizon_seconds: 5.0
    emit:
      tag: red_light_stop_line_crossed
      intent: supporting

  - id: red_light_running
    kind: single_frame
    subject: sdc_agent
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
        - operator: predicate.red_light_crossing_transition
          args:
            max_lateral_m: 2.0
            max_before_stop_line_m: 12.0
            min_after_stop_line_m: 0.5
            max_after_stop_line_m: 15.0
            min_speed_mps: 0.5
            max_heading_delta_rad: 0.7
            max_lane_heading_change_rad: 0.35
            lane_heading_lookahead_m: 15.0
            max_future_heading_change_rad: 0.25
            future_heading_horizon_seconds: 2.0
            extended_max_future_heading_change_rad: 0.45
            extended_future_heading_horizon_seconds: 5.0
    emit:
      tag: red_light_running
      intent: review
      policy:
        cooldown_frames: 30
        episode:
          by: subject
          mode: interval

  # --- SDC Hard Braking / Emergency Braking ---
  - id: sdc_hard_braking
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.pair_types_are
          args:
            ego_type: vehicle
        - operator: predicate.pair_ego_hard_braking
          args:
            other_types: [vehicle, pedestrian, cyclist]
            window_seconds: 1.0
            max_acceleration_mps2: -3.0
            min_speed_drop_mps: 2.0
            min_start_speed_mps: 3.0
            max_front_longitudinal_m: 35.0
            max_lateral_m: 4.0
            traffic_control_max_stop_longitudinal_m: 40.0
            traffic_control_max_stop_lateral_m: 4.0
            traffic_control_target_margin_m: 5.0
    emit:
      tag: sdc_hard_braking
      intent: review
      metadata:
        review_family: sdc_response
        review_priority: 30
      policy:
        cooldown_frames: 20
        episode:
          by: subject
          mode: interval

  # --- VRU Close Interaction ---
  - id: vru_close_interaction
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.vru_close_interaction
          args:
            vru_types: [pedestrian, cyclist]
            min_longitudinal_m: 0.0
            behind_min_longitudinal_m: -2.0
            behind_close_distance_m: 5.0
            max_longitudinal_m: 16.0
            max_lateral_m: 5.0
            max_distance_m: 12.0
            min_ego_speed_mps: 0.5
            min_closing_speed_mps: 0.2
            close_lateral_m: 3.5
            wide_lateral_min_closing_speed_mps: 1.5
            immediate_distance_m: 6.0
            max_ttc_s: 4.0
            high_immediate_distance_m: 4.5
            high_max_ttc_s: 2.5
            high_close_lateral_m: 3.0
            high_ttc_lateral_m: 3.5
            high_ego_response_max_distance_m: 10.0
            ego_response_window_seconds: 1.0
            ego_response_max_acceleration_mps2: -2.0
            ego_response_min_speed_drop_mps: 1.0
            type_thresholds:
              pedestrian:
                max_distance_m: 10.0
                max_lateral_m: 4.0
                close_lateral_m: 3.0
                high_close_lateral_m: 2.6
                high_ttc_lateral_m: 3.2
                min_closing_speed_mps: 0.8
                wide_lateral_min_closing_speed_mps: 1.5
              cyclist:
                max_distance_m: 12.0
                max_lateral_m: 5.0
                close_lateral_m: 3.5
                high_close_lateral_m: 3.0
                high_ttc_lateral_m: 4.0
                min_closing_speed_mps: 0.5
                wide_lateral_min_closing_speed_mps: 1.2
    emit:
      tag: vru_close_interaction
      intent: review
      metadata:
        review_family: vru
        review_priority: 20
      policy:
        cooldown_frames: 20
        episode:
          by: subject
          mode: interval

  # --- Lane-change Conflict ---
  - id: lane_change_conflict
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.sdc_lane_change_conflict
          args:
            window_seconds: 3.0
            max_lane_lateral_m: 1.8
            target_lane_lateral_m: 2.2
            max_heading_delta_rad: 0.7
            min_lateral_displacement_m: 1.5
            max_front_longitudinal_m: 25.0
            max_behind_longitudinal_m: 20.0
            max_lateral_m: 3.0
            max_ttc_s: 4.0
            min_closing_speed_mps: 0.5
            min_target_speed_mps: 1.0
    emit:
      tag: lane_change_conflict
      intent: review
      metadata:
        review_family: lane_change
        review_priority: 20
      policy:
        cooldown_frames: 20
        episode:
          by: subject
          mode: interval

  # --- SDC Repeated Lane Change ---
  - id: sdc_repeated_lane_change
    kind: single_frame
    subject: sdc_agent
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
        - operator: predicate.sdc_repeated_lane_change
          args:
            window_seconds: 3.0
            min_lane_changes: 2
            max_lateral_m: 1.5
            max_heading_delta_rad: 0.7
            min_speed_mps: 2.0
            min_stable_frames: 2
            min_lateral_displacement_m: 2.5
    emit:
      tag: sdc_repeated_lane_change
      intent: review
      policy:
        cooldown_frames: 30
        episode:
          by: subject
          mode: interval
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
