from asyncio import create_task
from html import escape

from pyscript import web, when

from models import (
    GENERAL_MODE,
    NUMBERS_MODE,
    QUIZ_MODES,
    TABS,
    VERBS_MODE,
    app_state,
    ui_state,
)
from parsing import load_library
from session import (
    advance_to_next,
    apply_text_hint,
    apply_verb_hint,
    back_to_config,
    current_card,
    has_wrong_cards,
    reset_stats_and_wrong,
    start_run,
    stats_totals,
    submit_current_answer,
)
from storage import clear_persistence, hydrate_persistence, persist_persistence
from table_gen import build_review_view
from utils import normalize_answer, sanitize_int, sanitize_ratio

_persisted_store = None

TEXT_RESULT_RESET_CLASSES = (
    "text-red-800",
    "font-bold",
    "border-red-700",
    "bg-red-50",
)
TEXT_INPUT_RESET_CLASSES = (
    "text-green-800",
    "font-bold",
    "border-green-700",
    "bg-green-50",
    "text-red-800",
    "border-red-700",
    "bg-red-50",
    "focus:outline-none",
    "focus:ring-0",
)
TEXT_INPUT_OK_CLASSES = (
    "text-green-800",
    "font-bold",
    "border-green-700",
    "bg-green-50",
    "focus:outline-none",
    "focus:ring-0",
)
TEXT_FORM_RESET_CLASSES = (
    "border",
    "border-green-600",
    "bg-green-100",
    "border-red-600",
    "bg-red-100",
    "rounded-xl",
    "p-3",
)
TEXT_FORM_OK_CLASSES = (
    "border",
    "border-green-600",
    "bg-green-100",
    "rounded-xl",
    "p-3",
)
TEXT_FORM_BAD_CLASSES = (
    "border",
    "border-red-600",
    "bg-red-100",
    "rounded-xl",
    "p-3",
)


def el(element_id):
    return web.page[element_id]


def set_hidden(element_id, hidden):
    node = el(element_id)
    if node is None:
        return
    if hidden:
        node.classes.add("hidden")
    else:
        node.classes.discard("hidden")


def set_text(element_id, value):
    node = el(element_id)
    if node is None:
        return
    node.textContent = str(value)


def set_html(element_id, value):
    node = el(element_id)
    if node is None:
        return
    node.innerHTML = str(value)


def set_value(element_id, value):
    node = el(element_id)
    if node is None:
        return
    node.value = str(value)


def _set_classes(node, *, remove_classes=(), add_classes=()):
    if node is None:
        return
    for class_name in remove_classes:
        node.classList.remove(class_name)
    for class_name in add_classes:
        node.classList.add(class_name)


def _render_template(template_id, values):
    node = el(template_id)
    if node is None:
        return ""
    markup = str(node.innerHTML or "")
    for key, value in values.items():
        markup = markup.replace("{{" + key + "}}", str(value))
    return markup


def _schedule_persist():
    if _persisted_store is None:
        return
    create_task(persist_persistence(app_state, ui_state, _persisted_store))


def _sync_ratio_labels(mcq_ratio):
    mcq_value = sanitize_ratio(mcq_ratio, 50)
    text_value = 100 - mcq_value
    set_text("mcq-ratio-label", f"{mcq_value}%")
    set_text("text-ratio-label", f"{text_value}%")


def _sync_full_ratio_label(full_ratio):
    full_value = sanitize_ratio(full_ratio, 50)
    set_text("full-ratio-label", f"{full_value}%")


def set_active_tab(tab_name):
    if tab_name not in TABS:
        tab_name = "quiz"
    ui_state.active_tab = tab_name

    for tab in TABS:
        button = el(f"tab-{tab}")
        section = el(f"section-{tab}")
        if button is not None:
            button.classes.discard("btn-primary")
            button.classes.discard("btn-outline")
            button.classes.add("btn-primary" if tab == tab_name else "btn-outline")
        if section is not None:
            if tab == tab_name:
                section.classes.discard("hidden")
            else:
                section.classes.add("hidden")


def _render_error():
    if ui_state.error:
        set_hidden("app-error", False)
        set_text("app-error-text", ui_state.error)
    else:
        set_hidden("app-error", True)
        set_text("app-error-text", "")


def _render_config():
    config = app_state.session.run_config

    set_value("quiz-mode", ui_state.selected_quiz_mode)
    set_value("max-cards", config.max_cards)
    mcq_ratio = sanitize_ratio(config.mcq_ratio, 50)
    text_ratio = 100 - mcq_ratio
    config.mcq_ratio = mcq_ratio
    config.text_ratio = text_ratio
    config.full_ratio = sanitize_ratio(config.full_ratio, 50)
    set_value("mcq-ratio", mcq_ratio)
    set_value("full-ratio", config.full_ratio)
    _sync_ratio_labels(mcq_ratio)
    _sync_full_ratio_label(config.full_ratio)

    mode = ui_state.selected_quiz_mode
    set_hidden("failed-only-wrap", False)

    failed_only_el = el("failed-only")
    if failed_only_el is not None:
        wrong_count = len(app_state.stats.wrong_card_ids)
        failed_unavailable = wrong_count == 0
        failed_only_el.disabled = failed_unavailable
        if failed_unavailable:
            failed_only_el.checked = False
            config.failed_only = False
            set_text(
                "failed-only-note",
                "No wrong cards yet. This option unlocks after mistakes are tracked.",
            )
        else:
            failed_only_el.checked = bool(config.failed_only)
            set_text(
                "failed-only-note", f"{wrong_count} wrong card(s) currently tracked."
            )

    set_hidden("verbs-full-wrap", mode != VERBS_MODE)


def _render_mcq(card):
    feedback = app_state.session.feedback
    selected = ""
    if feedback:
        selected = normalize_answer(feedback.answers.get("answer", ""))
    accepted = {normalize_answer(answer) for answer in card.accepted_answers}

    parts = []
    for choice in card.choices:
        normalized = normalize_answer(choice)
        btn_class = "mcq-choice mcq-choice-default"
        if feedback:
            if normalized == selected and feedback.correct:
                btn_class = "mcq-choice mcq-choice-correct"
            elif normalized == selected and not feedback.correct:
                btn_class = "mcq-choice mcq-choice-wrong"
            elif normalized in accepted:
                btn_class = "mcq-choice mcq-choice-correct"
            else:
                btn_class = "mcq-choice mcq-choice-muted"
        parts.append(
            _render_template(
                "tpl-mcq-choice",
                {
                    "choice_attr": escape(str(choice), quote=True),
                    "choice_text": escape(str(choice)),
                    "choice_class": btn_class
                    + (" pointer-events-none" if feedback else ""),
                },
            )
        )
    set_html("mcq-choices", "".join(parts))


def _render_text(card):
    feedback = app_state.session.feedback
    is_correct = bool(feedback and feedback.correct)
    is_wrong = bool(feedback and not feedback.correct)
    answer_el = el("text-answer")
    result_el = el("text-answer-result")
    hint_btn = el("text-hint-btn")
    form_el = el("text-answer-form")

    if result_el is not None:
        result_el.classList.add("hidden")
        _set_classes(result_el, remove_classes=TEXT_RESULT_RESET_CLASSES)
        result_el.innerHTML = ""

    if answer_el is not None:
        answer_el.value = app_state.session.text_answer
        answer_el.disabled = False
        answer_el.readOnly = bool(feedback)
        _set_classes(answer_el, remove_classes=TEXT_INPUT_RESET_CLASSES)
        if is_correct:
            _set_classes(answer_el, add_classes=TEXT_INPUT_OK_CLASSES)
        elif is_wrong:
            answer_el.classList.add("hidden")
            if result_el is not None:
                wrong = str(feedback.answers.get("answer", ""))
                corrected = str(feedback.expected.get("answer", ""))
                result_el.classList.remove("hidden")
                _set_classes(
                    result_el,
                    add_classes=(
                        "inline-flex",
                        "text-red-800",
                        "font-bold",
                        "border-red-700",
                        "bg-red-50",
                    ),
                )
                if wrong.strip():
                    result_el.innerHTML = _render_template(
                        "tpl-text-result-wrong",
                        {
                            "wrong_text": escape(wrong),
                            "correct_text": escape(corrected),
                        },
                    )
                else:
                    result_el.innerHTML = _render_template(
                        "tpl-text-result-correct-only",
                        {"correct_text": escape(corrected)},
                    )
        else:
            answer_el.classList.remove("hidden")
    if hint_btn is not None:
        hint_btn.disabled = bool(feedback)

    if form_el is not None:
        _set_classes(form_el, remove_classes=TEXT_FORM_RESET_CLASSES)
        if is_correct:
            _set_classes(form_el, add_classes=TEXT_FORM_OK_CLASSES)
        elif is_wrong:
            _set_classes(form_el, add_classes=TEXT_FORM_BAD_CLASSES)

    feedback_el = el("text-feedback")
    if feedback_el is None:
        return

    feedback_el.className = "text-sm mt-2"
    feedback_el.textContent = ""


def _render_verb(card):
    feedback = app_state.session.feedback
    parts = []
    expected_map = feedback.expected if feedback else {}
    answer_map = feedback.answers if feedback else {}

    for field in card.verb_fields:
        value = app_state.session.verb_answers.get(field.key, "")
        input_class = "input input-bordered"
        row_class = ""
        result_class = "input input-bordered hidden items-center"
        result_html = ""

        if feedback:
            expected_value = str(expected_map.get(field.key, field.answer))
            provided_value = str(answer_map.get(field.key, ""))
            is_wrong = normalize_answer(provided_value) != normalize_answer(
                expected_value
            )

            if is_wrong:
                input_class += " hidden"
                row_class = "border border-red-600 bg-red-100 rounded-xl p-3"
                result_class = (
                    "input input-bordered inline-flex items-center text-red-800 "
                    "font-bold border-red-700 bg-red-50"
                )
                if provided_value.strip():
                    result_html = _render_template(
                        "tpl-text-result-wrong",
                        {
                            "wrong_text": escape(provided_value),
                            "correct_text": escape(expected_value),
                        },
                    )
                else:
                    result_html = _render_template(
                        "tpl-text-result-correct-only",
                        {"correct_text": escape(expected_value)},
                    )
            else:
                row_class = "border border-green-600 bg-green-100 rounded-xl p-3"
                input_class += (
                    " text-green-800 font-bold border-green-700 bg-green-50 "
                    "focus:outline-none focus:ring-0"
                )

        parts.append(
            _render_template(
                "tpl-verb-field",
                {
                    "row_class": row_class,
                    "field_label": escape(field.label),
                    "field_key": escape(field.key, quote=True),
                    "input_class": input_class,
                    "field_value": escape(str(value), quote=True),
                    "result_class": result_class,
                    "result_html": result_html,
                    "readonly_attr": "readonly" if feedback else "",
                    "hint_disabled": "disabled" if feedback else "",
                },
            )
        )
    set_html("verb-fields", "".join(parts))

    feedback_el = el("verb-feedback")
    if feedback_el is None:
        return
    feedback_el.className = "text-sm mt-2"
    if not feedback:
        feedback_el.textContent = ""
        return

    if feedback.correct:
        feedback_el.textContent = "All verb forms are correct"
        feedback_el.classList.add("ok")
    else:
        feedback_el.textContent = ""
        feedback_el.classList.add("bad")


def _render_study():
    session = app_state.session
    in_study = session.stage == "study"
    completed = session.stage == "complete"
    set_hidden("quiz-config", in_study or completed)
    set_hidden("quiz-study", not in_study)
    set_hidden("quiz-complete", not completed)

    if in_study:
        card = current_card(app_state)
        if not card:
            set_text("study-meta", "No cards in this run")
            return

        set_text(
            "study-meta",
            f"{card.mode} | Card {session.index + 1} of {len(session.queue)}",
        )
        set_text("study-prompt-primary", card.prompt_primary)
        set_text("study-prompt-secondary", card.prompt_secondary)

        show_audio = card.prompt_kind == "audio" and bool(card.prompt_audio_url)
        set_hidden("study-audio-wrap", not show_audio)
        if show_audio:
            audio_el = el("study-audio")
            if audio_el is not None:
                audio_el.src = card.prompt_audio_url

        set_hidden("mcq-wrap", card.answer_kind != "mcq")
        set_hidden("text-wrap", card.answer_kind != "text")
        set_hidden("verb-wrap", card.answer_kind != "verb")

        if card.answer_kind == "mcq":
            _render_mcq(card)
        elif card.answer_kind == "text":
            _render_text(card)
        else:
            _render_verb(card)

        next_button = el("next-card-btn")
        if next_button is not None:
            next_button.disabled = not bool(session.feedback)

    if completed:
        summary = session.summary
        accuracy = 0
        if summary.answered:
            accuracy = int((summary.correct * 100) / summary.answered)
        set_text("complete-total", summary.total_cards)
        set_text("complete-accuracy", f"{accuracy}%")
        set_text("complete-correct", summary.correct)
        set_text("complete-incorrect", summary.incorrect)


def _render_stats():
    totals = stats_totals(app_state)
    set_text("stats-attempts", totals["attempts"])
    set_text("stats-correct", totals["correct"])
    set_text("stats-incorrect", totals["incorrect"])
    set_text("stats-accuracy", f"{totals['accuracy']}%")
    set_text("stats-failed", totals["failedCount"])

    if totals["attempts"] == 0:
        set_text("stats-insight", "Start a run to populate stats.")
    elif totals["failedCount"] == 0:
        set_text("stats-insight", "Great work. No wrong cards are currently tracked.")
    else:
        set_text(
            "stats-insight",
            f"You currently have {totals['failedCount']} wrong card(s). Use failed-only mode to revise them.",
        )


def _render_review():
    mode = ui_state.selected_review_mode
    if mode not in QUIZ_MODES:
        mode = GENERAL_MODE
        ui_state.selected_review_mode = mode

    set_value("review-mode", mode)

    selected_key = ""
    if mode == GENERAL_MODE:
        selected_key = ui_state.selected_review_general_key
    elif mode == NUMBERS_MODE:
        selected_key = ui_state.selected_review_numbers_key

    view = build_review_view(app_state.library, mode, selected_key)

    if mode == GENERAL_MODE:
        ui_state.selected_review_general_key = view["resolved_key"]
    elif mode == NUMBERS_MODE:
        ui_state.selected_review_numbers_key = view["resolved_key"]

    set_hidden("review-key-wrap", not view["show_key_selector"])
    set_text("review-key-label", view["key_label"])
    set_html("review-key", view["key_options_html"])
    if view["show_key_selector"]:
        set_value("review-key", view["resolved_key"])

    set_html("review-table", view["table_html"])


def render():
    set_hidden("loading-section", not ui_state.loading)
    set_active_tab(ui_state.active_tab)
    _render_error()
    _render_config()
    _render_study()
    _render_review()
    _render_stats()


def _read_run_config_from_form():
    config = app_state.session.run_config

    mode_input = el("quiz-mode")
    mode_value = mode_input.value if mode_input is not None else GENERAL_MODE
    if mode_value not in QUIZ_MODES:
        mode_value = GENERAL_MODE

    config.quiz_mode = mode_value
    ui_state.selected_quiz_mode = mode_value

    failed_only = el("failed-only")
    config.failed_only = bool(
        failed_only and failed_only.checked and not failed_only.disabled
    )
    config.max_cards = sanitize_int(
        (el("max-cards").value if el("max-cards") else 20), 20, 1, 500
    )
    config.mcq_ratio = sanitize_ratio(
        (el("mcq-ratio").value if el("mcq-ratio") else 50), 50
    )
    config.text_ratio = 100 - config.mcq_ratio
    config.full_ratio = sanitize_ratio(
        (el("full-ratio").value if el("full-ratio") else 50), 50
    )

    if config.quiz_mode == GENERAL_MODE:
        if config.mcq_ratio <= 0 and config.text_ratio <= 0:
            ui_state.error = (
                "Set at least one non-zero ratio for multiple-choice or type-in."
            )
            return False
    elif config.quiz_mode == VERBS_MODE:
        if config.mcq_ratio <= 0 and config.text_ratio <= 0 and config.full_ratio <= 0:
            ui_state.error = (
                "Set a non-zero ratio for multiple-choice, type-in, or full cards."
            )
            return False
    elif config.quiz_mode == NUMBERS_MODE:
        if config.mcq_ratio <= 0 and config.text_ratio <= 0:
            ui_state.error = "Set at least one non-zero ratio for numbers answer type."
            return False

    if config.failed_only and not has_wrong_cards(app_state):
        config.failed_only = False
    return True


def _refresh_text_answer_from_ui():
    answer_el = el("text-answer")
    if answer_el is not None:
        lowered = str(answer_el.value or "").lower()
        app_state.session.text_answer = lowered
        answer_el.value = lowered


def _refresh_verb_answers_from_ui():
    card = current_card(app_state)
    if not card:
        return
    if card.answer_kind != "verb":
        return
    for field in card.verb_fields:
        node = el(f"verb-input-{field.key}")
        if node is not None:
            lowered = str(node.value or "").lower()
            app_state.session.verb_answers[field.key] = lowered
            node.value = lowered


@when("click", "#tabs-nav")
def on_tab_click(event):
    target = event.target
    if not target:
        return
    button = target.closest("button[data-tab]")
    if not button:
        return
    set_active_tab(button.getAttribute("data-tab") or "quiz")
    _schedule_persist()
    render()


@when("change", "#quiz-mode")
def on_quiz_mode_change(event):
    mode = event.target.value
    if mode in QUIZ_MODES:
        ui_state.selected_quiz_mode = mode
        app_state.session.run_config.quiz_mode = mode
    render()


@when("change", "#review-mode")
def on_review_mode_change(event):
    mode = event.target.value
    if mode in QUIZ_MODES:
        ui_state.selected_review_mode = mode
    render()


@when("change", "#review-key")
def on_review_key_change(event):
    key = str(event.target.value or "")
    mode = ui_state.selected_review_mode
    if mode == GENERAL_MODE:
        ui_state.selected_review_general_key = key
    elif mode == NUMBERS_MODE:
        ui_state.selected_review_numbers_key = key
    render()


@when("input", "#mcq-ratio")
def on_mcq_ratio_change(event):
    mcq_ratio = sanitize_ratio(event.target.value, 50)
    app_state.session.run_config.mcq_ratio = mcq_ratio
    app_state.session.run_config.text_ratio = 100 - mcq_ratio
    _sync_ratio_labels(mcq_ratio)


@when("input", "#full-ratio")
def on_full_ratio_change(event):
    full_ratio = sanitize_ratio(event.target.value, 50)
    app_state.session.run_config.full_ratio = full_ratio
    _sync_full_ratio_label(full_ratio)


@when("submit", "#quiz-config-form")
def on_quiz_start(event):
    event.preventDefault()
    ui_state.error = None
    if not _read_run_config_from_form():
        render()
        return
    start_run(app_state)
    if (
        app_state.session.summary.total_cards == 0
        and app_state.session.run_config.failed_only
    ):
        ui_state.error = "No wrong cards are available for the selected mode. Disable failed-only to continue."
        back_to_config(app_state)
    _schedule_persist()
    render()


@when("submit", "#text-answer-form")
def on_text_submit(event):
    event.preventDefault()
    ui_state.error = None
    _refresh_text_answer_from_ui()
    submit_current_answer(app_state, text_answer=app_state.session.text_answer)
    _schedule_persist()
    render()


@when("submit", "#verb-answer-form")
def on_verb_submit(event):
    event.preventDefault()
    ui_state.error = None
    _refresh_verb_answers_from_ui()
    submit_current_answer(app_state, verb_answers=app_state.session.verb_answers)
    _schedule_persist()
    render()


@when("input", "#text-answer")
def on_text_input(event):
    lowered = str(event.target.value or "").lower()
    app_state.session.text_answer = lowered
    event.target.value = lowered


@when("input", "#verb-fields")
def on_verb_input(event):
    target = event.target
    if not target:
        return
    key = target.getAttribute("data-field") or ""
    if not key:
        return
    lowered = str(target.value or "").lower()
    app_state.session.verb_answers[key] = lowered
    target.value = lowered


@when("click", "#app")
def on_app_click(event):
    target = event.target
    if not target:
        return

    action_button = target.closest("button[data-action]")
    if action_button:
        action = action_button.getAttribute("data-action") or ""
        if action == "answer-choice":
            choice = action_button.getAttribute("data-choice") or ""
            submit_current_answer(app_state, choice_answer=choice)
        elif action == "verb-hint":
            field_key = action_button.getAttribute("data-field") or ""
            apply_verb_hint(app_state, field_key)
        _schedule_persist()
        render()
        return

    target_id = target.id or ""
    if target_id == "text-hint-btn":
        apply_text_hint(app_state)
    elif target_id == "next-card-btn":
        advance_to_next(app_state)
    elif target_id == "stop-run-btn":
        back_to_config(app_state)
    elif target_id == "back-to-config-btn":
        back_to_config(app_state)
    elif target_id == "stats-reset-btn":
        reset_stats_and_wrong(app_state)
        if _persisted_store is not None:
            create_task(clear_persistence(app_state, ui_state, _persisted_store))
    else:
        return

    _schedule_persist()
    render()


@when("error", "#study-audio")
def on_audio_error(event):
    card = current_card(app_state)
    if not card:
        return
    if card.prompt_kind != "audio":
        return

    fallback_text = str(card.metadata.get("fallback_text") or "")
    card.prompt_kind = "text"
    if fallback_text:
        card.prompt_primary = fallback_text
    card.prompt_secondary = "Audio unavailable. Continue with text prompt."
    render()


async def bootstrap():
    global _persisted_store

    ui_state.loading = True
    ui_state.error = None
    render()

    try:
        app_state.library = await load_library()
        _persisted_store = await hydrate_persistence(app_state, ui_state)
        ui_state.ready = True
    except Exception as error:
        ui_state.error = str(error)
    finally:
        ui_state.loading = False
        if ui_state.active_tab not in TABS:
            ui_state.active_tab = "quiz"
        render()


create_task(bootstrap())
