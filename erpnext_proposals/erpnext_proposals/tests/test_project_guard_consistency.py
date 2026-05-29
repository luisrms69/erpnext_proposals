"""
Tests for assert_can_create_project state guard and JS↔Python contract.

Regression tests for the bug fixed in PR #22: the guard incorrectly accepted
"Aprobada" and "Enviada al Cliente" instead of requiring "Ganada" only.

Two classes:
- TestProjectGuardStates  — unit tests on the Python guard directly.
- TestProjectGuardJSContract — contract test: _projectStates in quotation.js
  must match what the Python guard accepts. If they diverge, this test fails.
"""

import os
import re
import unittest

import frappe

from erpnext_proposals.erpnext_proposals.utils.proposal_versioning import (
	assert_can_create_project,
)

_VALID_STATE = "Ganada"
_INVALID_STATES = [
	"Borrador",
	"En Revision",
	"Aprobada",
	"Enviada al Cliente",
	"Rechazada",
	None,
	"",
]


def _doc(workflow_state):
	"""Minimal submitted Quotation mock — no group, no project, no superseded."""
	return frappe._dict(
		{
			"docstatus": 1,
			"workflow_state": workflow_state,
			"superseded_by_proposal": None,
			"proposal_group": None,
			"proposal_project": None,
			"name": "_TEST-GUARD",
		}
	)


class TestProjectGuardStates(unittest.TestCase):
	"""assert_can_create_project must accept only Ganada and reject everything else."""

	def test_valid_state_ganada_passes_guard(self):
		"""Ganada + submitted + no superseded/group/project must pass without raising."""
		assert_can_create_project(_doc(_VALID_STATE))

	def test_ganada_with_existing_project_passes_guard(self):
		"""
		Ganada + proposal_project already set (and project EXISTS in DB) + not superseded must pass.

		This is the idempotency/update path: clicking 'Ver / Actualizar Proyecto'
		on a Quotation that already has a project must reach project.py's
		idempotency block, not be blocked here.
		The guard's job is state and superseded — not project existence.

		Uses mock to simulate an existing project in DB (the real-world scenario that
		was failing: clicking the button a second time after the project was created).
		"""
		from unittest.mock import patch

		doc = frappe._dict(
			{
				"docstatus": 1,
				"workflow_state": "Ganada",
				"superseded_by_proposal": None,
				"proposal_group": None,
				"proposal_project": "PROJ-0036",  # already has a project
				"name": "_TEST-GUARD-WITH-PROJ",
			}
		)
		with patch("frappe.db.exists", return_value="PROJ-0036"):
			assert_can_create_project(doc)  # must not raise

	def test_invalid_states_raise_validation_error(self):
		"""Every non-Ganada state (including None and empty string) must raise ValidationError."""
		for state in _INVALID_STATES:
			with self.subTest(workflow_state=state):
				with self.assertRaises(
					frappe.exceptions.ValidationError,
					msg=f"Expected ValidationError for workflow_state={state!r}",
				):
					assert_can_create_project(_doc(state))


class TestProjectGuardJSContract(unittest.TestCase):
	"""
	Contract test: _projectStates in quotation.js must equal [_VALID_STATE].

	Reads quotation.js, extracts the _projectStates array that controls
	"Crear Proyecto" button visibility, and asserts it matches the Python guard.

	If this test fails, the UI button and assert_can_create_project have diverged
	and a state could be reachable in the UI but blocked (or open) in the backend.
	"""

	_JS_PATH = os.path.normpath(
		os.path.join(os.path.dirname(__file__), "..", "..", "public", "js", "quotation.js")
	)

	def test_js_project_states_match_python_guard(self):
		self.assertTrue(
			os.path.exists(self._JS_PATH),
			f"quotation.js not found at {self._JS_PATH}",
		)

		with open(self._JS_PATH) as f:
			content = f.read()

		match = re.search(r"const\s+_projectStates\s*=\s*(\[.*?\])", content)
		self.assertIsNotNone(
			match,
			"Could not find `_projectStates` in quotation.js. "
			"If the variable was renamed, update this test to match.",
		)

		raw = match.group(1)
		js_states = re.findall(r'["\']([^"\']+)["\']', raw)

		self.assertEqual(
			js_states,
			[_VALID_STATE],
			f"JS _projectStates {js_states!r} != Python guard state {[_VALID_STATE]!r}. "
			"Keep quotation.js and assert_can_create_project in sync.",
		)
