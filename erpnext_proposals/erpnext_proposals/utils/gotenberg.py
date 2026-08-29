"""Adapter mínimo para Gotenberg (ADR-0015).

Cliente HTTP delgado sobre la API oficial de Gotenberg:

- HTML → PDF:  ``POST /forms/chromium/convert/html``  (multipart: index.html + header/footer opcionales)
- Merge:       ``POST /forms/pdfengines/merge``       (multipart de PDFs)

Principios (ADR-0015):

- **Fail closed:** si un formato pide Gotenberg y no hay endpoint configurado, se lanza error claro.
  NUNCA hay fallback silencioso a wkhtmltopdf.
- **Endpoint = configuración del entorno**, no del cliente ni hardcodeado (clave
  ``proposal_gotenberg_url`` en site/common config).
- Sin dependencias nuevas: usa ``requests`` (ya presente en Frappe).
- Sin retries / colas / circuit breakers en esta fase (solo timeout + error claro).
"""

import frappe
import requests
from frappe import _

# Clave de configuración del entorno (site_config.json o common_site_config.json). NO del cliente.
GOTENBERG_CONF_KEY = "proposal_gotenberg_url"

# Timeout HTTP por defecto (segundos). Suficiente para una propuesta; sin retries.
DEFAULT_TIMEOUT = 30

CHROMIUM_CONVERT_PATH = "/forms/chromium/convert/html"
MERGE_PATH = "/forms/pdfengines/merge"


def get_gotenberg_url() -> str:
	"""Devuelve la URL base de Gotenberg desde la configuración del entorno.

	Fail closed: si la clave no está configurada, lanza error (no hay fallback silencioso)."""
	url = (frappe.conf.get(GOTENBERG_CONF_KEY) or "").strip()
	if not url:
		frappe.throw(
			_(
				"Gotenberg no está configurado: falta la clave '{0}' en site_config.json / "
				"common_site_config.json. El Print Format solicita el renderer 'gotenberg-v1' y no "
				"se hace fallback a wkhtmltopdf."
			).format(GOTENBERG_CONF_KEY)
		)
	return url.rstrip("/")


def _stringify(options: dict | None) -> dict:
	"""Convierte opciones a los strings de formulario que espera Gotenberg (bool → 'true'/'false')."""
	out: dict = {}
	for key, value in (options or {}).items():
		if isinstance(value, bool):
			out[key] = "true" if value else "false"
		else:
			out[key] = str(value)
	return out


class GotenbergClient:
	"""Cliente HTTP mínimo para Gotenberg. Construirlo valida el endpoint (fail closed)."""

	def __init__(self, base_url: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> None:
		self.base_url = (base_url or get_gotenberg_url()).rstrip("/")
		self.timeout = timeout

	def _post(self, path: str, files: list, data: dict | None = None) -> bytes:
		"""POST multipart y devuelve el PDF binario. Error claro (sin fallback) ante fallo o no-200."""
		try:
			resp = requests.post(f"{self.base_url}{path}", files=files, data=data or {}, timeout=self.timeout)
		except requests.RequestException as exc:
			frappe.throw(_("No se pudo contactar a Gotenberg en {0}: {1}").format(self.base_url, str(exc)))

		if resp.status_code != 200:
			# Incluir status + fragmento de respuesta en el error técnico, sin volcar basura al usuario.
			snippet = (resp.text or "")[:500]
			frappe.throw(
				_("Gotenberg respondió {0} en {1}. Respuesta: {2}").format(resp.status_code, path, snippet)
			)
		return resp.content

	def html_to_pdf(
		self,
		index_html: str,
		header_html: str | None = None,
		footer_html: str | None = None,
		options: dict | None = None,
	) -> bytes:
		"""Convierte HTML → PDF. ``index.html`` es obligatorio; header/footer son opcionales y se
		renderizan en el contexto Chromium separado de Gotenberg (recursos ya inline)."""
		files = [("files", ("index.html", index_html.encode("utf-8"), "text/html"))]
		if header_html:
			files.append(("files", ("header.html", header_html.encode("utf-8"), "text/html")))
		if footer_html:
			files.append(("files", ("footer.html", footer_html.encode("utf-8"), "text/html")))
		return self._post(CHROMIUM_CONVERT_PATH, files, _stringify(options))

	def merge(self, pdfs: list[tuple[str, bytes]]) -> bytes:
		"""Fusiona PDFs en Gotenberg (``pypdf`` NO participa del merge contractual).

		Gotenberg fusiona por **orden alfanumérico del nombre de archivo**, así que se antepone un
		índice numérico para garantizar el orden recibido (p. ej. cover → body)."""
		files = [
			("files", (f"{i}_{name}", content, "application/pdf")) for i, (name, content) in enumerate(pdfs)
		]
		return self._post(MERGE_PATH, files)
