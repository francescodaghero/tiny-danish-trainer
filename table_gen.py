from html import escape

from models import GENERAL_MODE, NUMBERS_MODE, VERBS_MODE


def _render_select_options(options, selected_value):
	parts = []
	for value, label in options:
		selected_attr = " selected" if value == selected_value else ""
		parts.append(
			f'<option value="{escape(str(value), quote=True)}"{selected_attr}>'
			f"{escape(str(label))}</option>"
		)
	return "".join(parts)


def _render_empty(message):
	return (
		'<div class="rounded-xl border border-base-300 bg-base-100 p-4 text-sm text-base-content/70">'
		f"{escape(message)}"
		"</div>"
	)


def _render_table(headers, rows):
	header_html = "".join(
		f'<th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-base-content/60">{escape(str(header))}</th>'
		for header in headers
	)

	body_rows = []
	for row in rows:
		cells = "".join(
			f'<td class="px-4 py-3 align-top text-sm text-base-content">{escape(str(cell))}</td>'
			for cell in row
		)
		body_rows.append(f"<tr class=\"border-t border-base-200\">{cells}</tr>")

	body_html = "".join(body_rows)
	return (
		'<div class="overflow-x-auto rounded-xl border border-base-300 bg-base-100">'
		'<table class="min-w-full divide-y divide-base-200">'
		f"<thead class=\"bg-base-200/60\"><tr>{header_html}</tr></thead>"
		f"<tbody class=\"divide-y divide-base-200\">{body_html}</tbody>"
		"</table>"
		"</div>"
	)


def _resolve_selected_key(keys, selected_key):
	if selected_key in keys:
		return selected_key
	return keys[0] if keys else ""


def _general_keys(library):
	keys = {str(row.group) for row in library.general_entries if str(row.group).strip()}
	return sorted(keys)


def _numbers_keys(library):
	keys = {str(row.kind) for row in library.number_entries if str(row.kind).strip()}
	return sorted(keys)


def _verbs_table(library):
	entries = list(library.verb_entries)
	if not entries:
		return _render_empty("No verb entries loaded.")

	form_specs = [
		("infinitive", "Infinitive"),
		("imperative", "Imperative"),
		("present", "Present"),
		("past", "Past"),
		("past_participle", "Past participle"),
	]
	active_specs = [
		spec
		for spec in form_specs
		if any(str(getattr(row, spec[0], "")).strip() for row in entries)
	]

	headers = ["English", *[label for _, label in active_specs]]
	rows = []
	for row in entries:
		values = [row.english]
		for key, _ in active_specs:
			values.append(str(getattr(row, key, "") or "-"))
		rows.append(values)
	return _render_table(headers, rows)


def _general_table(library, group_key):
	if not group_key:
		return _render_empty("No general group available.")
	rows = [
		[row.english, row.translation]
		for row in library.general_entries
		if str(row.group) == group_key
	]
	if not rows:
		return _render_empty("No entries found for this group.")
	return _render_table(["English", "Translation"], rows)


def _numbers_table(library, number_key):
	if not number_key:
		return _render_empty("No numbers key available.")
	rows = [
		[row.label, row.value]
		for row in library.number_entries
		if str(row.kind) == number_key
	]
	if not rows:
		return _render_empty("No entries found for this key.")
	return _render_table(["Label", "Value"], rows)


def build_review_view(library, mode, selected_key):
	normalized_mode = mode if mode in (GENERAL_MODE, VERBS_MODE, NUMBERS_MODE) else GENERAL_MODE

	if normalized_mode == VERBS_MODE:
		return {
			"show_key_selector": False,
			"key_label": "",
			"key_options_html": "",
			"resolved_key": "",
			"table_html": _verbs_table(library),
		}

	if normalized_mode == GENERAL_MODE:
		keys = _general_keys(library)
		resolved = _resolve_selected_key(keys, selected_key)
		return {
			"show_key_selector": True,
			"key_label": "General key",
			"key_options_html": _render_select_options([(key, key) for key in keys], resolved),
			"resolved_key": resolved,
			"table_html": _general_table(library, resolved),
		}

	keys = _numbers_keys(library)
	resolved = _resolve_selected_key(keys, selected_key)
	return {
		"show_key_selector": True,
		"key_label": "Numbers key",
		"key_options_html": _render_select_options([(key, key) for key in keys], resolved),
		"resolved_key": resolved,
		"table_html": _numbers_table(library, resolved),
	}
