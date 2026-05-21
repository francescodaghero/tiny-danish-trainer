from pyscript import storage

from models import AppState, CardStats, PERSISTENCE_NAME, UIState


def _serialize_stats(app_state: AppState):
    card_stats = {}
    for card_id, row in app_state.stats.card_stats.items():
        card_stats[card_id] = {
            "attempts": int(row.attempts),
            "correct": int(row.correct),
            "incorrect": int(row.incorrect),
        }

    return {
        "card_stats": card_stats,
        "wrong_card_ids": sorted(app_state.stats.wrong_card_ids),
    }


def _deserialize_stats(raw):
    card_stats = {}
    for card_id, row in dict(raw.get("card_stats") or {}).items():
        if not isinstance(row, dict):
            continue
        card_stats[str(card_id)] = CardStats(
            attempts=int(row.get("attempts", 0)),
            correct=int(row.get("correct", 0)),
            incorrect=int(row.get("incorrect", 0)),
        )

    wrong = raw.get("wrong_card_ids") or []
    wrong_ids = {str(item) for item in wrong if str(item).strip()}
    return card_stats, wrong_ids


async def hydrate_persistence(app_state: AppState, ui_state: UIState):
    persisted = await storage(PERSISTENCE_NAME)

    raw_stats = persisted.get("stats")
    if isinstance(raw_stats, dict):
        card_stats, wrong_ids = _deserialize_stats(raw_stats)
        app_state.stats.card_stats = card_stats
        app_state.stats.wrong_card_ids = wrong_ids

    raw_ui = persisted.get("ui")
    if isinstance(raw_ui, dict):
        tab = str(raw_ui.get("active_tab", "train"))
        if tab in ("train", "stats"):
            ui_state.active_tab = tab

    return persisted


async def persist_persistence(app_state: AppState, ui_state: UIState, persisted):
    persisted["stats"] = _serialize_stats(app_state)
    persisted["ui"] = {"active_tab": ui_state.active_tab}
    await persisted.sync()


async def clear_persistence(app_state: AppState, ui_state: UIState, persisted):
    app_state.stats.card_stats = {}
    app_state.stats.wrong_card_ids = set()
    ui_state.active_tab = "train"
    persisted.clear()
    await persisted.sync()
