import hashlib
import random

from models import (
    AUDIO_BASE_PATH,
    GENERAL_MODE,
    NUMBERS_MODE,
    VERBS_MODE,
    StudyCard,
    VerbField,
)
from utils import normalize_answer, sanitize_int, sanitize_ratio


def _make_id(seed):
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:24]


def _pick_confusers(correct, universe, count=3):
    pool = [
        item for item in universe if normalize_answer(item) != normalize_answer(correct)
    ]
    random.shuffle(pool)
    return pool[:count]


def _build_mcq(correct, universe):
    choices = [correct] + _pick_confusers(correct, universe)
    deduped = []
    seen = set()
    for item in choices:
        key = normalize_answer(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    random.shuffle(deduped)
    return deduped


def _weighted_answer_kind(run_config, allow_audio=False):
    weights = []
    if run_config.text_ratio > 0:
        weights.append(("text", run_config.text_ratio))
    if run_config.mcq_ratio > 0:
        weights.append(("mcq", run_config.mcq_ratio))

    if not weights:
        return "text"

    total = sum(weight for _, weight in weights)
    roll = random.randint(1, total)
    current = 0
    for label, weight in weights:
        current += weight
        if roll <= current:
            return label
    return weights[-1][0]


def _apply_failed_only(cards, app_state, failed_only):
    if not failed_only:
        return cards
    if not app_state.stats.wrong_card_ids:
        return []
    allowed = app_state.stats.wrong_card_ids
    return [card for card in cards if card.id in allowed]


def _build_preposition_card(row, *, index, run_config, universe):
    answer_text = str(row.translation or "")
    normalized_answer = normalize_answer(answer_text)
    non_empty_universe = [item for item in universe if normalize_answer(item)]
    can_build_mcq = bool(normalized_answer) and len(set(non_empty_universe)) >= 2

    answer_kind = _weighted_answer_kind(run_config, allow_audio=False)
    if answer_kind == "mcq" and not can_build_mcq:
        answer_kind = "text"

    card_id = _make_id(f"preposition|{index}|{row.english}|{answer_text}|{answer_kind}")
    mcq_universe = non_empty_universe if can_build_mcq else []

    return StudyCard(
        id=card_id,
        mode=GENERAL_MODE,
        domain="general:prepositions",
        prompt_kind="text",
        answer_kind="mcq" if answer_kind == "mcq" else "text",
        prompt_primary=row.english,
        prompt_secondary="Fill in the preposition",
        accepted_answers=[answer_text],
        choices=_build_mcq(answer_text, mcq_universe) if answer_kind == "mcq" else [],
    )


def build_general_cards(app_state, run_config):
    entries = list(app_state.library.general_entries)
    group_universes: dict[str, list[str]] = {}
    for row in entries:
        group_name = str(row.group or "default")
        group_universes.setdefault(group_name, []).append(row.translation)
    cards = []

    for index, row in enumerate(entries):
        group_name = str(row.group or "default")
        universe = group_universes.get(group_name, [row.translation])

        if group_name.lower() == "prepositions":
            cards.append(
                _build_preposition_card(
                    row,
                    index=index,
                    run_config=run_config,
                    universe=universe,
                )
            )
            continue

        can_build_mcq = len(universe) >= 2

        answer_kind = _weighted_answer_kind(run_config, allow_audio=False)
        if answer_kind == "mcq" and not can_build_mcq:
            answer_kind = "text"

        card_id = _make_id(
            f"general|{group_name}|{index}|{row.english}|{row.translation}|{answer_kind}"
        )
        choices = _build_mcq(row.translation, universe) if answer_kind == "mcq" else []
        cards.append(
            StudyCard(
                id=card_id,
                mode=GENERAL_MODE,
                domain=f"general:{group_name}",
                prompt_kind="text",
                answer_kind="mcq" if answer_kind == "mcq" else "text",
                prompt_primary=row.english,
                prompt_secondary="Translate to Danish",
                accepted_answers=[row.translation],
                choices=choices,
            )
        )

    return cards


def build_verb_cards(app_state, run_config):
    entries = list(app_state.library.verb_entries)
    full_ratio = sanitize_ratio(run_config.full_ratio, 50)
    full_total = int(round((len(entries) * full_ratio) / 100))
    full_total = max(0, min(len(entries), full_total))
    full_indices = (
        set(random.sample(range(len(entries)), full_total)) if full_total else set()
    )
    use_simple_cards = run_config.mcq_ratio > 0 or run_config.text_ratio > 0

    infinitive_universe = [row.infinitive for row in entries]
    english_universe = [row.english for row in entries]

    cards = []
    for index, row in enumerate(entries):
        if use_simple_cards:
            answer_kind_a = _weighted_answer_kind(run_config, allow_audio=False)
            card_id_a = _make_id(
                f"verb-a|{index}|{row.english}|{row.infinitive}|{answer_kind_a}"
            )
            cards.append(
                StudyCard(
                    id=card_id_a,
                    mode=VERBS_MODE,
                    domain="verbs",
                    prompt_kind="text",
                    answer_kind="mcq" if answer_kind_a == "mcq" else "text",
                    prompt_primary=row.english,
                    prompt_secondary="Infinitive",
                    accepted_answers=[row.infinitive],
                    choices=(
                        _build_mcq(row.infinitive, infinitive_universe)
                        if answer_kind_a == "mcq"
                        else []
                    ),
                )
            )

        if use_simple_cards:
            answer_kind_b = _weighted_answer_kind(run_config, allow_audio=False)
            card_id_b = _make_id(
                f"verb-b|{index}|{row.infinitive}|{row.english}|{answer_kind_b}"
            )
            cards.append(
                StudyCard(
                    id=card_id_b,
                    mode=VERBS_MODE,
                    domain="verbs",
                    prompt_kind="text",
                    answer_kind="mcq" if answer_kind_b == "mcq" else "text",
                    prompt_primary=row.infinitive,
                    prompt_secondary="English",
                    accepted_answers=[row.english],
                    choices=(
                        _build_mcq(row.english, english_universe)
                        if answer_kind_b == "mcq"
                        else []
                    ),
                )
            )

        if index in full_indices:
            card_id_c = _make_id(f"verb-c|{index}|{row.english}|all")
            cards.append(
                StudyCard(
                    id=card_id_c,
                    mode=VERBS_MODE,
                    domain="verbs",
                    prompt_kind="text",
                    answer_kind="verb",
                    prompt_primary=row.english,
                    prompt_secondary="Fill all forms",
                    verb_fields=[
                        VerbField("infinitive", "Infinitive", row.infinitive),
                        *(
                            [VerbField("imperative", "Imperative", row.imperative)]
                            if str(row.imperative).strip()
                            else []
                        ),
                        VerbField("present", "Present", row.present),
                        VerbField("past", "Past", row.past),
                        VerbField(
                            "past_participle", "Past participle", row.past_participle
                        ),
                    ],
                    accepted_answers=[row.infinitive],
                )
            )

    return cards


def _numbers_audio_choices(label, available_labels):
    sorted_labels = sorted(set(available_labels))
    if label not in sorted_labels:
        return []
    index = sorted_labels.index(label)
    neighbors = []
    for offset in range(1, 8):
        left = index - offset
        right = index + offset
        if left >= 0:
            neighbors.append(sorted_labels[left])
        if right < len(sorted_labels):
            neighbors.append(sorted_labels[right])
        if len(neighbors) >= 6:
            break
    random.shuffle(neighbors)
    return neighbors[:3]


def build_number_cards(app_state, run_config):
    entries = list(app_state.library.number_entries)
    label_universe = [row.label for row in entries]
    cards = []

    for index, row in enumerate(entries):
        answer_kind = _weighted_answer_kind(run_config, allow_audio=False)
        audio_url = f"{AUDIO_BASE_PATH}/{row.label}.mp3"
        card_id = _make_id(
            f"num-audio-only|{index}|{row.label}|{row.value}|{answer_kind}"
        )
        audio_choices = [row.label] + _numbers_audio_choices(row.label, label_universe)
        random.shuffle(audio_choices)
        cards.append(
            StudyCard(
                id=card_id,
                mode=NUMBERS_MODE,
                domain="numbers",
                prompt_kind="audio",
                answer_kind="mcq" if answer_kind == "mcq" else "text",
                prompt_primary="Listen to the audio",
                prompt_secondary=f"{row.kind}: answer with the spoken word",
                prompt_audio_url=audio_url,
                accepted_answers=[row.label],
                choices=audio_choices if answer_kind == "mcq" else [],
                metadata={"fallback_text": row.label},
            )
        )
    return cards


def build_run_cards(app_state, run_config):
    if run_config.quiz_mode == GENERAL_MODE:
        cards = build_general_cards(app_state, run_config)
    elif run_config.quiz_mode == VERBS_MODE:
        cards = build_verb_cards(app_state, run_config)
    else:
        cards = build_number_cards(app_state, run_config)

    cards = _apply_failed_only(cards, app_state, run_config.failed_only)
    random.shuffle(cards)
    return cards[: sanitize_int(run_config.max_cards, 20, 1, 500)]
