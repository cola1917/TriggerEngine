from __future__ import annotations

import yaml

from .ast import (
    AllCondition,
    EventCompactionPolicy,
    EventPolicy,
    OperatorCall,
    PairConfig,
    ReviewEpisodePolicy,
    Rule,
    RuleDiagnostic,
    RuleEmit,
    RuleSet,
    RuleWindow,
    SequenceStep,
    SequenceTagCondition,
    SustainedTagCondition,
    _VALID_INTENTS,
)


class RuleParseError(Exception):
    pass


_VALID_SUBJECTS = {"frame", "agent", "lane", "scenario", "agent_pair", "sdc_agent", "sdc_pair"}


class RuleParser:
    def parse_yaml(self, text: str) -> RuleSet:
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise RuleParseError(f"Invalid YAML: {exc}") from exc

        if not isinstance(doc, dict) or "rules" not in doc:
            raise RuleParseError("Top-level 'rules' key is required")

        rules_raw = doc["rules"]
        if not isinstance(rules_raw, list):
            raise RuleParseError("'rules' must be a list")

        seen_ids: set[str] = set()
        rules: list[Rule] = []
        diagnostics: list[RuleDiagnostic] = []

        for i, rule_raw in enumerate(rules_raw):
            rule = self._parse_rule(rule_raw, i, diagnostics)
            if rule.rule_id in seen_ids:
                raise RuleParseError(f"Duplicate rule id: '{rule.rule_id}'")
            seen_ids.add(rule.rule_id)
            rules.append(rule)

        return RuleSet(rules=tuple(rules), diagnostics=tuple(diagnostics))

    def _parse_rule(self, raw: dict, index: int, diagnostics: list[RuleDiagnostic]) -> Rule:
        if not isinstance(raw, dict):
            raise RuleParseError(f"rules[{index}] must be a dict")

        rule_id = raw.get("id")
        if not rule_id:
            raise RuleParseError(f"rules[{index}].id is required")

        subject = raw.get("subject", "frame")
        if subject not in _VALID_SUBJECTS:
            raise RuleParseError(
                f"rules[{index}].subject must be one of {_VALID_SUBJECTS}, got '{subject}'"
            )

        kind = raw.get("kind", "single_frame")
        if kind not in ("single_frame", "temporal"):
            raise RuleParseError(
                f"rules[{index}].kind must be 'single_frame' or 'temporal', got '{kind}'"
            )

        description = raw.get("description")
        required_modalities = self._parse_required_modalities(raw, index)

        window_raw = raw.get("window")
        window = None
        if window_raw is not None:
            if not isinstance(window_raw, dict):
                raise RuleParseError(f"rules[{index}].window must be a dict")
            window = RuleWindow(history_steps=window_raw.get("history_steps"))

        when_raw = raw.get("when")
        if not isinstance(when_raw, dict):
            raise RuleParseError(f"rules[{index}].when must be a dict")

        if kind == "temporal":
            condition = self._parse_temporal_condition(when_raw, index, rule_id, diagnostics)
        else:
            if "all" not in when_raw:
                raise RuleParseError(f"rules[{index}].when.all is required")
            condition = self._parse_all_condition(when_raw["all"], index, rule_id, diagnostics)

        emit_raw = raw.get("emit")
        if not isinstance(emit_raw, dict):
            raise RuleParseError(f"rules[{index}].emit must be a dict")

        tag_name = emit_raw.get("tag")
        if not tag_name:
            raise RuleParseError(f"rules[{index}].emit.tag is required")

        metadata = emit_raw.get("metadata", {})
        if not isinstance(metadata, dict):
            raise RuleParseError(f"rules[{index}].emit.metadata must be a dict")

        intent = emit_raw.get("intent", "debug")
        if intent not in _VALID_INTENTS:
            raise RuleParseError(
                f"rules[{index}].emit.intent must be one of {_VALID_INTENTS}, got '{intent}'"
            )

        policy = self._parse_policy(emit_raw, index, intent)

        emit = RuleEmit(
            tag_name=tag_name,
            value=emit_raw.get("value", True),
            metadata=metadata,
            policy=policy,
            intent=intent,
        )

        pair = self._parse_pair(raw, subject, index)

        return Rule(
            rule_id=rule_id,
            subject_type=subject,
            condition=condition,
            emit=emit,
            kind=kind,
            description=description,
            window=window,
            pair=pair,
            required_modalities=required_modalities,
        )

    def _parse_required_modalities(self, raw: dict, rule_index: int) -> frozenset[str]:
        modalities_raw = raw.get("required_modalities")
        if modalities_raw is None:
            return frozenset()
        if not isinstance(modalities_raw, list):
            raise RuleParseError(f"rules[{rule_index}].required_modalities must be a list")
        modalities = []
        for i, modality in enumerate(modalities_raw):
            if not isinstance(modality, str) or not modality:
                raise RuleParseError(
                    f"rules[{rule_index}].required_modalities[{i}] must be a non-empty string"
                )
            modalities.append(modality)
        return frozenset(modalities)

    def _parse_temporal_condition(
        self,
        when_raw: dict,
        rule_index: int,
        rule_id: str,
        diagnostics: list[RuleDiagnostic],
    ) -> SustainedTagCondition | SequenceTagCondition:
        # Temporal rules compose previously emitted tags. They should not call
        # operators directly because the compiler validates tag-to-rule links.
        if "all" in when_raw:
            raise RuleParseError(
                f"rules[{rule_index}] is temporal and must not contain 'when.all' with operators"
            )

        if "sequence" in when_raw:
            return self._parse_sequence_condition(when_raw, rule_index, rule_id, diagnostics)

        tag_name = when_raw.get("tag")
        if not tag_name:
            raise RuleParseError(f"rules[{rule_index}].when.tag is required for temporal rules")

        sustained_raw = when_raw.get("sustained")
        if not isinstance(sustained_raw, dict):
            raise RuleParseError(f"rules[{rule_index}].when.sustained must be a dict")

        frames = sustained_raw.get("frames")
        seconds = sustained_raw.get("seconds")

        if frames is not None and seconds is not None:
            raise RuleParseError(
                f"rules[{rule_index}].when.sustained must not have both 'frames' and 'seconds'"
            )

        if frames is not None:
            if not isinstance(frames, int) or frames <= 0:
                raise RuleParseError(
                    f"rules[{rule_index}].when.sustained.frames must be a positive integer"
                )
            self._record_deprecated_frame_window(
                diagnostics,
                rule_id,
                f"rules[{rule_index}].when.sustained.frames",
                "Use when.sustained.seconds so the rule is independent of source frame rate.",
            )
            return SustainedTagCondition(tag_name=tag_name, frames=frames)

        if seconds is not None:
            if not isinstance(seconds, (int, float)) or seconds <= 0:
                raise RuleParseError(
                    f"rules[{rule_index}].when.sustained.seconds must be a positive number"
                )
            return SustainedTagCondition(tag_name=tag_name, seconds=float(seconds))

        raise RuleParseError(
            f"rules[{rule_index}].when.sustained must have either 'frames' or 'seconds'"
        )

    def _parse_sequence_condition(
        self,
        when_raw: dict,
        rule_index: int,
        rule_id: str,
        diagnostics: list[RuleDiagnostic],
    ) -> SequenceTagCondition:
        sequence_raw = when_raw.get("sequence")
        if not isinstance(sequence_raw, list):
            raise RuleParseError(f"rules[{rule_index}].when.sequence must be a list")

        steps: list[SequenceStep] = []
        for i, step_raw in enumerate(sequence_raw):
            if not isinstance(step_raw, dict):
                raise RuleParseError(
                    f"rules[{rule_index}].when.sequence[{i}] must be a dict"
                )
            tag_name = step_raw.get("tag")
            if not tag_name:
                raise RuleParseError(
                    f"rules[{rule_index}].when.sequence[{i}].tag is required"
                )
            steps.append(SequenceStep(tag_name=tag_name))

        within_frames = when_raw.get("within_frames")
        within_seconds = when_raw.get("within_seconds")

        if within_frames is not None and within_seconds is not None:
            raise RuleParseError(
                f"rules[{rule_index}].when must not have both 'within_frames' and 'within_seconds'"
            )

        if within_frames is not None:
            if not isinstance(within_frames, int) or within_frames <= 0:
                raise RuleParseError(
                    f"rules[{rule_index}].when.within_frames must be a positive integer"
                )
            self._record_deprecated_frame_window(
                diagnostics,
                rule_id,
                f"rules[{rule_index}].when.within_frames",
                "Use when.within_seconds so the sequence window is independent of source frame rate.",
            )
        elif within_seconds is not None:
            if not isinstance(within_seconds, (int, float)) or within_seconds <= 0:
                raise RuleParseError(
                    f"rules[{rule_index}].when.within_seconds must be a positive number"
                )
            within_seconds = float(within_seconds)
        else:
            raise RuleParseError(
                f"rules[{rule_index}].when must have either 'within_frames' or 'within_seconds'"
            )

        max_gap_frames = when_raw.get("max_gap_frames")
        if max_gap_frames is not None:
            if not isinstance(max_gap_frames, int) or max_gap_frames < 0:
                raise RuleParseError(
                    f"rules[{rule_index}].when.max_gap_frames must be a non-negative integer"
                )

        return SequenceTagCondition(
            steps=tuple(steps),
            within_frames=within_frames,
            within_seconds=within_seconds,
            max_gap_frames=max_gap_frames,
        )

    def _parse_all_condition(
        self,
        calls_raw: list,
        rule_index: int,
        rule_id: str,
        diagnostics: list[RuleDiagnostic],
    ) -> AllCondition:
        if not isinstance(calls_raw, list):
            raise RuleParseError(f"rules[{rule_index}].when.all must be a list")

        calls: list[OperatorCall] = []
        for i, call_raw in enumerate(calls_raw):
            if not isinstance(call_raw, dict):
                raise RuleParseError(
                    f"rules[{rule_index}].when.all[{i}] must be a dict"
                )

            operator_name = call_raw.get("operator")
            if not operator_name:
                raise RuleParseError(
                    f"rules[{rule_index}].when.all[{i}].operator is required"
                )

            args = call_raw.get("args", {})
            if not isinstance(args, dict):
                raise RuleParseError(
                    f"rules[{rule_index}].when.all[{i}].args must be a dict"
                )

            for_last_n_frames = call_raw.get("for_last_n_frames")
            if for_last_n_frames is not None:
                self._record_deprecated_frame_window(
                    diagnostics,
                    rule_id,
                    f"rules[{rule_index}].when.all[{i}].for_last_n_frames",
                    "Use a seconds-based operator argument or window before removing frame-rate compatibility.",
                )

            call = OperatorCall(
                operator_name=operator_name,
                args=args,
                for_last_n_frames=for_last_n_frames,
            )
            calls.append(call)

        return AllCondition(calls=tuple(calls))

    def _record_deprecated_frame_window(
        self,
        diagnostics: list[RuleDiagnostic],
        rule_id: str,
        field_path: str,
        message: str,
    ) -> None:
        diagnostics.append(
            RuleDiagnostic(
                level="warning",
                code="deprecated_frame_window",
                message=message,
                rule_id=rule_id,
                field_path=field_path,
            )
        )

    def _parse_policy(self, emit_raw: dict, rule_index: int, intent: str = "debug") -> EventPolicy:
        policy_raw = emit_raw.get("policy")
        if policy_raw is None:
            return EventPolicy()

        if not isinstance(policy_raw, dict):
            raise RuleParseError(f"rules[{rule_index}].emit.policy must be a dict")

        valid_keys = {"cooldown_frames", "compact", "episode"}
        unknown = set(policy_raw.keys()) - valid_keys
        if unknown:
            raise RuleParseError(
                f"rules[{rule_index}].emit.policy has unknown keys: {unknown}"
            )

        cooldown = policy_raw.get("cooldown_frames", 0)
        if not isinstance(cooldown, int) or cooldown < 0:
            raise RuleParseError(
                f"rules[{rule_index}].emit.policy.cooldown_frames must be a non-negative integer"
            )

        compact = self._parse_compact(policy_raw, rule_index, intent)
        episode = self._parse_episode(policy_raw, rule_index, intent)

        return EventPolicy(cooldown_frames=cooldown, compact=compact, episode=episode)

    def _parse_compact(
        self, policy_raw: dict, rule_index: int, intent: str
    ) -> EventCompactionPolicy | None:
        compact_raw = policy_raw.get("compact")
        if compact_raw is None:
            return None

        if intent == "review":
            raise RuleParseError(
                f"rules[{rule_index}].emit.policy.compact is not allowed with intent 'review'"
            )

        if not isinstance(compact_raw, dict):
            raise RuleParseError(f"rules[{rule_index}].emit.policy.compact must be a dict")

        by = compact_raw.get("by", "subject")
        if by != "subject":
            raise RuleParseError(
                f"rules[{rule_index}].emit.policy.compact.by must be 'subject', got '{by}'"
            )

        mode = compact_raw.get("mode", "interval")
        if mode != "interval":
            raise RuleParseError(
                f"rules[{rule_index}].emit.policy.compact.mode must be 'interval', got '{mode}'"
            )

        valid_keys = {"by", "mode"}
        unknown = set(compact_raw.keys()) - valid_keys
        if unknown:
            raise RuleParseError(
                f"rules[{rule_index}].emit.policy.compact has unknown keys: {unknown}"
            )

        return EventCompactionPolicy(by=by, mode=mode)

    def _parse_episode(
        self, policy_raw: dict, rule_index: int, intent: str
    ) -> ReviewEpisodePolicy | None:
        episode_raw = policy_raw.get("episode")
        if episode_raw is None:
            return None

        if intent != "review":
            raise RuleParseError(
                f"rules[{rule_index}].emit.policy.episode is only allowed with intent 'review'"
            )

        if not isinstance(episode_raw, dict):
            raise RuleParseError(f"rules[{rule_index}].emit.policy.episode must be a dict")

        by = episode_raw.get("by", "subject")
        if by != "subject":
            raise RuleParseError(
                f"rules[{rule_index}].emit.policy.episode.by must be 'subject', got '{by}'"
            )

        mode = episode_raw.get("mode", "interval")
        if mode != "interval":
            raise RuleParseError(
                f"rules[{rule_index}].emit.policy.episode.mode must be 'interval', got '{mode}'"
            )

        valid_keys = {"by", "mode"}
        unknown = set(episode_raw.keys()) - valid_keys
        if unknown:
            raise RuleParseError(
                f"rules[{rule_index}].emit.policy.episode has unknown keys: {unknown}"
            )

        return ReviewEpisodePolicy(by=by, mode=mode)

    def _parse_pair(self, raw: dict, subject: str, rule_index: int) -> PairConfig:
        pair_raw = raw.get("pair")
        if pair_raw is None:
            return PairConfig()

        if subject != "agent_pair":
            raise RuleParseError(
                f"rules[{rule_index}].pair is only allowed for subject 'agent_pair', got '{subject}'"
            )

        if not isinstance(pair_raw, dict):
            raise RuleParseError(f"rules[{rule_index}].pair must be a dict")

        mode = pair_raw.get("mode", "directed")
        if mode not in ("directed", "unordered"):
            raise RuleParseError(
                f"rules[{rule_index}].pair.mode must be 'directed' or 'unordered', got '{mode}'"
            )

        valid_keys = {"mode"}
        unknown = set(pair_raw.keys()) - valid_keys
        if unknown:
            raise RuleParseError(
                f"rules[{rule_index}].pair has unknown keys: {unknown}"
            )

        return PairConfig(mode=mode)
