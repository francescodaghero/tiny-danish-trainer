from card_gen import build_run_cards
from models import (
    AppState,
    CardStats,
    FeedbackState,
    RunSummary,
    StudyCard,
)
from utils import normalize_answer


def has_wrong_cards(app_state: AppState):
    return len(app_state.stats.wrong_card_ids) > 0


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
