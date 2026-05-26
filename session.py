import hashlib
import random

from models import (
    AUDIO_BASE_PATH,
    GENERAL_MODE,
    NUMBERS_MODE,
    VERBS_MODE,
    AppState,
    CardStats,
    FeedbackState,
    NumberEntry,
    RunConfig,
    RunSummary,
    StudyCard,
    VerbField,
)


def normalize_answer(value):
    return str(value or "").strip().lower()


def sanitize_int(value, default_value, minimum=1, maximum=10_000):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default_value
    return max(minimum, min(maximum, parsed))


def sanitize_ratio(value, default_value):
    return sanitize_int(value, default_value, 0, 100)


def has_wrong_cards(app_state: AppState):
    return len(app_state.stats.wrong_card_ids) > 0


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


def _weighted_answer_kind(run_config: RunConfig, allow_audio=False):
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


def _apply_failed_only(cards, app_state: AppState, failed_only):
    if not failed_only:
        return cards
    if not app_state.stats.wrong_card_ids:
        return []
    allowed = app_state.stats.wrong_card_ids
    return [card for card in cards if card.id in allowed]


def _build_preposition_card(row, *, index, run_config, universe):
    # Preposition cards always prompt with the sentence and answer with preposition text.
    answer_text = str(row.translation or "")
    normalized_answer = normalize_answer(answer_text)
    non_empty_universe = [item for item in universe if normalize_answer(item)]
    can_build_mcq = bool(normalized_answer) and len(set(non_empty_universe)) >= 2

    answer_kind = _weighted_answer_kind(run_config, allow_audio=False)
    if answer_kind == "mcq" and not can_build_mcq:
        answer_kind = "text"

    card_id = _make_id(
        f"preposition|{index}|{row.english}|{answer_text}|{answer_kind}"
    )
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


def build_general_cards(app_state: AppState, run_config: RunConfig):
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


def build_verb_cards(app_state: AppState, run_config: RunConfig):
    entries = list(app_state.library.verb_entries)
    full_ratio = sanitize_ratio(run_config.full_ratio, 50)
    full_total = int(round((len(entries) * full_ratio) / 100))
    full_total = max(0, min(len(entries), full_total))
    full_indices = (
        set(random.sample(range(len(entries)), full_total)) if full_total else set()
    )
    use_simple_cards = run_config.mcq_ratio > 0 or run_config.text_ratio > 0

    infinitive_universe = [row.infinitive for row in entries]
    tense_universe = []
    for row in entries:
        for form in [row.imperative, row.present, row.past, row.past_participle]:
            if str(form).strip():
                tense_universe.append(form)

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

        tense_rows = []
        if str(row.imperative).strip():
            tense_rows.append(("imperative", row.imperative))
        if str(row.present).strip():
            tense_rows.append(("present", row.present))
        if str(row.past).strip():
            tense_rows.append(("past", row.past))
        if str(row.past_participle).strip():
            tense_rows.append(("past_participle", row.past_participle))
        if use_simple_cards and tense_rows:
            tense_key, tense_value = random.choice(tense_rows)
            answer_kind_b = _weighted_answer_kind(run_config, allow_audio=False)
            card_id_b = _make_id(
                f"verb-b|{index}|{row.infinitive}|{tense_key}|{answer_kind_b}"
            )
            cards.append(
                StudyCard(
                    id=card_id_b,
                    mode=VERBS_MODE,
                    domain="verbs",
                    prompt_kind="text",
                    answer_kind="mcq" if answer_kind_b == "mcq" else "text",
                    prompt_primary=row.infinitive,
                    prompt_secondary=f"{tense_key} form",
                    accepted_answers=[tense_value],
                    choices=(
                        _build_mcq(tense_value, tense_universe)
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


def build_number_cards(app_state: AppState, run_config: RunConfig):
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


def build_run_cards(app_state: AppState, run_config: RunConfig):
    if run_config.training_mode == GENERAL_MODE:
        cards = build_general_cards(app_state, run_config)
    elif run_config.training_mode == VERBS_MODE:
        cards = build_verb_cards(app_state, run_config)
    else:
        cards = build_number_cards(app_state, run_config)

    cards = _apply_failed_only(cards, app_state, run_config.failed_only)
    random.shuffle(cards)
    return cards[: sanitize_int(run_config.max_cards, 20, 1, 500)]


def current_card(app_state: AppState):
    queue = app_state.session.queue
    index = app_state.session.index
    if not queue:
        return None
    if index < 0 or index >= len(queue):
        return None
    return queue[index]


def start_run(app_state: AppState):
    run_config = app_state.session.run_config
    cards = build_run_cards(app_state, run_config)
    app_state.session.stage = "study"
    app_state.session.queue = cards
    app_state.session.index = 0
    app_state.session.feedback = None
    app_state.session.text_answer = ""
    app_state.session.text_hint_count = 0
    app_state.session.verb_answers = {}
    app_state.session.verb_hint_counts = {}
    app_state.session.summary = RunSummary(total_cards=len(cards))
    if not cards:
        app_state.session.summary.completed = True
        app_state.session.stage = "complete"


def _record_outcome(app_state: AppState, card: StudyCard, correct: bool):
    existing = app_state.stats.card_stats.get(card.id)
    stats = existing if isinstance(existing, CardStats) else CardStats()
    stats.attempts += 1
    if correct:
        stats.correct += 1
        if card.id in app_state.stats.wrong_card_ids:
            app_state.stats.wrong_card_ids.discard(card.id)
    else:
        stats.incorrect += 1
        app_state.stats.wrong_card_ids.add(card.id)
    app_state.stats.card_stats[card.id] = stats


def _evaluate_text(card: StudyCard, answer: str):
    normalized = normalize_answer(answer)
    expected = {"answer": card.accepted_answers[0] if card.accepted_answers else ""}
    accepted = {normalize_answer(row) for row in card.accepted_answers}
    correct = normalized in accepted
    return FeedbackState(correct=correct, answers={"answer": answer}, expected=expected)


def _evaluate_choice(card: StudyCard, answer: str):
    return _evaluate_text(card, answer)


def _evaluate_verb(card: StudyCard, answers: dict[str, str]):
    expected = {field.key: field.answer for field in card.verb_fields}
    correct = True
    for key, value in expected.items():
        if normalize_answer(answers.get(key, "")) != normalize_answer(value):
            correct = False
            break
    return FeedbackState(correct=correct, answers=dict(answers), expected=expected)


def submit_current_answer(
    app_state: AppState, *, text_answer="", choice_answer="", verb_answers=None
):
    card = current_card(app_state)
    if not card:
        return None
    if app_state.session.feedback:
        return app_state.session.feedback

    if card.answer_kind == "verb":
        feedback = _evaluate_verb(card, verb_answers or {})
    elif card.answer_kind == "mcq":
        feedback = _evaluate_choice(card, choice_answer)
    else:
        feedback = _evaluate_text(card, text_answer)

    app_state.session.feedback = feedback
    app_state.session.summary.answered += 1
    if feedback.correct:
        app_state.session.summary.correct += 1
    else:
        app_state.session.summary.incorrect += 1

    _record_outcome(app_state, card, feedback.correct)
    return feedback


def advance_to_next(app_state: AppState):
    if not app_state.session.feedback:
        return False

    if app_state.session.index >= len(app_state.session.queue) - 1:
        app_state.session.stage = "complete"
        app_state.session.summary.completed = True
        app_state.session.feedback = None
        return True

    app_state.session.index += 1
    app_state.session.feedback = None
    app_state.session.text_answer = ""
    app_state.session.text_hint_count = 0
    app_state.session.verb_answers = {}
    app_state.session.verb_hint_counts = {}
    return True


def back_to_config(app_state: AppState):
    app_state.session.stage = "config"
    app_state.session.queue = []
    app_state.session.index = 0
    app_state.session.feedback = None
    app_state.session.text_answer = ""
    app_state.session.text_hint_count = 0
    app_state.session.verb_answers = {}
    app_state.session.verb_hint_counts = {}


def apply_text_hint(app_state: AppState):
    card = current_card(app_state)
    if not card:
        return ""
    if not card.accepted_answers:
        return ""
    answer = card.accepted_answers[0]
    app_state.session.text_hint_count += 1
    reveal = min(len(answer), app_state.session.text_hint_count)
    hinted = answer[:reveal]
    app_state.session.text_answer = hinted
    return hinted


def apply_verb_hint(app_state: AppState, field_key: str):
    card = current_card(app_state)
    if not card:
        return ""

    target = None
    for field in card.verb_fields:
        if field.key == field_key:
            target = field.answer
            break

    if target is None:
        return ""

    old = app_state.session.verb_hint_counts.get(field_key, 0)
    new_count = old + 1
    app_state.session.verb_hint_counts[field_key] = new_count
    reveal = min(len(target), new_count)
    hinted = target[:reveal]
    app_state.session.verb_answers[field_key] = hinted
    return hinted


def stats_totals(app_state: AppState):
    attempts = 0
    correct = 0
    incorrect = 0
    for row in app_state.stats.card_stats.values():
        attempts += int(row.attempts)
        correct += int(row.correct)
        incorrect += int(row.incorrect)

    accuracy = round((correct / attempts) * 100) if attempts else 0
    return {
        "attempts": attempts,
        "correct": correct,
        "incorrect": incorrect,
        "accuracy": accuracy,
        "failedCount": len(app_state.stats.wrong_card_ids),
    }


def reset_stats_and_wrong(app_state: AppState):
    app_state.stats.card_stats = {}
    app_state.stats.wrong_card_ids = set()
