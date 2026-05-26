from pyscript.fetch import fetch

from models import (
    DECK_FILEPATH,
    NUMBERS_FILEPATH,
    VERBS_FILEPATH,
    GeneralEntry,
    LibraryState,
    NumberEntry,
    VerbEntry,
)


def _clean_text(value):
    return str(value or "").strip()


def _normalize_group_name(value):
    group_name = _clean_text(value)
    lowered = group_name.lower()
    if lowered == "preprositions":
        return "prepositions"
    return group_name


def _is_preposition_group(group_name):
    return _clean_text(group_name).lower() == "prepositions"


def _preposition_answer_text(value):
    if isinstance(value, list):
        tokens = [_clean_text(item) for item in value]
        if not tokens:
            return ""
        return " ".join(tokens).strip()
    if value is None:
        return ""
    return _clean_text(value)


async def _load_json(url):
    response = await fetch(url)
    if not response.ok:
        raise ValueError(f"Could not load {url} (HTTP {int(response.status)}).")
    return await response.json()


def _parse_general(raw_rows):
    # Backward-compatible support for both legacy array format and new grouped map.
    grouped_rows: dict[str, list[dict]] = {}
    if isinstance(raw_rows, list):
        grouped_rows["default"] = raw_rows
    elif isinstance(raw_rows, dict):
        for group_name, rows in raw_rows.items():
            clean_group = _normalize_group_name(group_name)
            if not clean_group:
                raise ValueError("deck.json group names must be non-empty strings.")
            if not isinstance(rows, list):
                raise ValueError(f"deck.json group '{clean_group}' must be an array.")
            grouped_rows[clean_group] = rows
    else:
        raise ValueError("deck.json must be an array or an object of grouped arrays.")

    parsed: list[GeneralEntry] = []
    for group_name, rows in grouped_rows.items():
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(
                    f"deck.json group '{group_name}' row {index + 1} must be an object."
                )

            if _is_preposition_group(group_name):
                english = _clean_text(row.get("sentence"))
                translation = _preposition_answer_text(row.get("preposition"))
                if not english:
                    raise ValueError(
                        f"deck.json group '{group_name}' row {index + 1} must include sentence."
                    )
            else:
                english = _clean_text(row.get("english"))
                translation = _clean_text(row.get("translation"))
                if not english or not translation:
                    raise ValueError(
                        f"deck.json group '{group_name}' row {index + 1} must include english and translation."
                    )

            parsed.append(
                GeneralEntry(
                    group=group_name,
                    english=english,
                    translation=translation,
                )
            )
    return parsed


def _parse_verbs(raw_rows):
    if not isinstance(raw_rows, list):
        raise ValueError("verbs.json must be an array of entries.")

    parsed: list[VerbEntry] = []
    for index, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            raise ValueError(f"verbs.json row {index + 1} must be an object.")

        english = _clean_text(row.get("english"))
        infinitive = _clean_text(row.get("infinite") or row.get("infinitive"))
        imperative = _clean_text(row.get("imperative"))
        present = _clean_text(row.get("present"))
        past = _clean_text(row.get("past"))
        past_participle = _clean_text(row.get("past_participle"))

        # Some valid verbs (for example modal verbs) have no imperative form.
        if not all([english, infinitive, present, past, past_participle]):
            raise ValueError(
                f"verbs.json row {index + 1} is missing required verb fields."
            )

        parsed.append(
            VerbEntry(
                english=english,
                infinitive=infinitive,
                imperative=imperative,
                present=present,
                past=past,
                past_participle=past_participle,
            )
        )
    return parsed


def _parse_numbers(raw_obj):
    if not isinstance(raw_obj, dict):
        raise ValueError("numbers.json must be an object with ordinal/cardinal arrays.")

    parsed: list[NumberEntry] = []
    for key in ("ordinal", "cardinal"):
        rows = raw_obj.get(key)
        if not isinstance(rows, list):
            raise ValueError(f"numbers.json key '{key}' must be an array.")

        for index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError(
                    f"numbers.json {key} row {index + 1} must be [label, value]."
                )

            label = _clean_text(row[0])
            try:
                value = int(row[1])
            except (TypeError, ValueError):
                raise ValueError(
                    f"numbers.json {key} row {index + 1} has non-integer value."
                )

            if not label:
                raise ValueError(
                    f"numbers.json {key} row {index + 1} must have a label."
                )

            parsed.append(NumberEntry(kind=key, label=label, value=value))
    return parsed


async def load_library():
    raw_general = await _load_json(DECK_FILEPATH)
    raw_verbs = await _load_json(VERBS_FILEPATH)
    raw_numbers = await _load_json(NUMBERS_FILEPATH)

    return LibraryState(
        general_entries=_parse_general(raw_general),
        verb_entries=_parse_verbs(raw_verbs),
        number_entries=_parse_numbers(raw_numbers),
    )
