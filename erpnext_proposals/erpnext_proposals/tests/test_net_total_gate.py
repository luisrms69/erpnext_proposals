"""Tests — gate de venta neta root vs addenda (Change Control v2, bloque B1).

`_validate_blocking` (transición Borrador→En Revisión) exige `net_total > 0` SOLO para propuestas root
(grupo normal). Para addendas `ROOT-ADD-NN` ese gate se relaja (una addenda de costo/plan/absorción o
puramente contractual puede tener venta neta 0). `proposal_template` y `proposal_cost_center` siguen siendo
obligatorios para AMBOS (requisito de formalización — no cambia en B1).

Se prueba `_validate_blocking` directamente (mismo patrón que el resto de la suite, p. ej.
`wfv_mod._maybe_enqueue_auto_project`), con docs ligeros `frappe._dict`: la función solo lee
`proposal_template`, `proposal_cost_center`, `net_total` y `proposal_group`.
"""

import unittest

import frappe
from frappe.exceptions import ValidationError

from erpnext_proposals.erpnext_proposals.utils import workflow_validations as wfv_mod

TEMPLATE = "_NTG Template"
COST_CENTER = "_NTG Cost Center"


def _doc(*, proposal_group=None, net_total=0, template=TEMPLATE, cost_center=COST_CENTER):
	return frappe._dict(
		proposal_template=template,
		proposal_cost_center=cost_center,
		net_total=net_total,
		proposal_group=proposal_group,
	)


class TestNetTotalGate(unittest.TestCase):
	# ── Root (grupo normal): net_total > 0 sigue obligatorio ──────────────────────────

	def test_root_net_total_zero_bloquea(self):
		"""Regresión: una propuesta root con venta neta 0 sigue bloqueada."""
		with self.assertRaises(ValidationError) as ctx:
			wfv_mod._validate_blocking(_doc(proposal_group="ROOT-A", net_total=0))
		self.assertIn("venta neta", str(ctx.exception).lower())

	def test_root_sin_grupo_net_total_zero_bloquea(self):
		"""Root sin `proposal_group` (None) también está sujeta al gate."""
		with self.assertRaises(ValidationError) as ctx:
			wfv_mod._validate_blocking(_doc(proposal_group=None, net_total=0))
		self.assertIn("venta neta", str(ctx.exception).lower())

	def test_root_net_total_positivo_pasa(self):
		"""Happy path root: template + cost center + venta neta > 0 → no bloquea."""
		wfv_mod._validate_blocking(_doc(proposal_group="ROOT-A", net_total=1000))

	# ── Addenda ROOT-ADD-NN: net_total 0 permitido ────────────────────────────────────

	def test_addenda_net_total_zero_pasa(self):
		"""Nuevo comportamiento B1: una addenda `ROOT-ADD-NN` con venta neta 0 NO se bloquea."""
		wfv_mod._validate_blocking(_doc(proposal_group="ROOT-A-ADD-01", net_total=0))

	def test_addenda_net_total_positivo_pasa(self):
		"""Una addenda con venta neta > 0 tampoco se bloquea."""
		wfv_mod._validate_blocking(_doc(proposal_group="ROOT-A-ADD-02", net_total=5000))

	def test_addenda_version_net_total_zero_pasa(self):
		"""Una versión de addenda conserva el grupo `ROOT-ADD-NN` → mismo relajamiento del gate."""
		wfv_mod._validate_blocking(_doc(proposal_group="ROOT-XYZ-ADD-07", net_total=0))

	# ── Template / Cost Center: obligatorios para AMBOS (no cambia en B1) ──────────────

	def test_root_sin_template_bloquea(self):
		with self.assertRaises(ValidationError) as ctx:
			wfv_mod._validate_blocking(_doc(proposal_group="ROOT-A", net_total=1000, template=None))
		self.assertIn("proposal template", str(ctx.exception).lower())

	def test_addenda_sin_template_bloquea(self):
		"""La addenda NO relaja `proposal_template`: sigue siendo requisito de formalización."""
		with self.assertRaises(ValidationError) as ctx:
			wfv_mod._validate_blocking(_doc(proposal_group="ROOT-A-ADD-01", net_total=0, template=None))
		self.assertIn("proposal template", str(ctx.exception).lower())

	def test_addenda_sin_cost_center_bloquea(self):
		"""La addenda NO relaja `proposal_cost_center`: sigue siendo requisito de formalización."""
		with self.assertRaises(ValidationError) as ctx:
			wfv_mod._validate_blocking(_doc(proposal_group="ROOT-A-ADD-01", net_total=0, cost_center=None))
		self.assertIn("cost center", str(ctx.exception).lower())

	def test_addenda_sin_template_no_menciona_venta_neta(self):
		"""Con addenda net_total 0 y template faltante, el único error es el template (no la venta neta)."""
		with self.assertRaises(ValidationError) as ctx:
			wfv_mod._validate_blocking(_doc(proposal_group="ROOT-A-ADD-01", net_total=0, template=None))
		self.assertNotIn("venta neta", str(ctx.exception).lower())
