from dataclasses import dataclass
from typing import Any, Optional, Dict
from unittest import SkipTest

from sybil import Example, Document
from sybil.example import NotEvaluated


class If:

    def __init__(self, default_reason: str) -> None:
        self.default_reason = default_reason

    def __call__(self, condition: Any, reason: Optional[str] = None) -> Optional[str]:
        if condition:
            return reason or self.default_reason
        return None


@dataclass
class SkipState:
    active: bool = True
    remove: bool = False
    exception: Optional[Exception] = None
    last_action: Optional[str] = None


class Skipper:

    def __init__(self) -> None:
        self.document_state: Dict[Document, SkipState] = {}

    def state_for(self, example: Example) -> SkipState:
        document = example.document
        if document not in self.document_state:
            self.document_state[document] = SkipState()
        return self.document_state[example.document]

    def install(self, example: Example, state: SkipState, reason: Optional[str]) -> None:
        document = example.document
        document.push_evaluator(self)
        if reason:
            namespace = document.namespace.copy()
            reason = reason.lstrip()
            if reason.startswith('if'):
                condition = reason[2:]
                reason = 'if_' + condition
                namespace['if_'] = If(condition)
            reason = eval(reason, namespace)
            if reason:
                state.exception = SkipTest(reason)
            else:
                state.active = False

    def remove(self, example: Example) -> None:
        document = example.document
        document.pop_evaluator(self)
        del self.document_state[document]

    def evaluate_skip_example(self, example: Example) -> None:
        state = self.state_for(example)
        action, reason = example.parsed

        if action not in ('start', 'next', 'end'):
            raise ValueError('Bad skip action: ' + action)
        if state.last_action is None and action not in ('start', 'next'):
            raise ValueError(f"'skip: {action}' must follow 'skip: start'")
        elif state.last_action and action != 'end':
            raise ValueError(f"'skip: {action}' cannot follow 'skip: {state.last_action}'")

        state.last_action = action

        if action == 'start':
            self.install(example, state, reason)
        elif action == 'next':
            self.install(example, state, reason)
            state.remove = True
        elif action == 'end':
            self.remove(example)
            if reason:
                raise ValueError("Cannot have condition on 'skip: end'")

    def evaluate_other_example(self, example: Example) -> None:
        state = self.state_for(example)
        if state.remove:
            self.remove(example)
        if not state.active:
            raise NotEvaluated()
        if state.exception is not None:
            raise state.exception

    def __call__(self, example: Example) -> None:
        if example.region.evaluator is self:
            self.evaluate_skip_example(example)
        else:
            self.evaluate_other_example(example)
