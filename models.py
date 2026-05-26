import dataclasses
from typing import Any, Optional

GENERAL_MODE = "general"
VERBS_MODE = "verbs"
NUMBERS_MODE = "numbers"
QUIZ_MODES = (GENERAL_MODE, VERBS_MODE, NUMBERS_MODE)
TABS = ("quiz", "stats")

DECK_FILEPATH = "./static/deck.json"
VERBS_FILEPATH = "./static/verbs.json"
NUMBERS_FILEPATH = "./static/numbers.json"
AUDIO_BASE_PATH = "./static/audio"
PERSISTENCE_NAME = "danish-web-progress-v1"


@dataclasses.dataclass
class DictLikeState:
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def update(self, values: Any) -> None:
        if dataclasses.is_dataclass(values):
            values = dataclasses.asdict(values)
        for key, value in dict(values).items():
            if hasattr(self, key):
                setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class GeneralEntry:
    group: str
    english: str
    translation: str


@dataclasses.dataclass
class VerbEntry:
    english: str
    infinitive: str
    imperative: str
    present: str
    past: str
    past_participle: str


@dataclasses.dataclass
class NumberEntry:
    kind: str
    label: str
    value: int


@dataclasses.dataclass
class VerbField(DictLikeState):
    key: str
    label: str
    answer: str


@dataclasses.dataclass
class StudyCard(DictLikeState):
    id: str
    mode: str
    domain: str
    prompt_kind: str
    answer_kind: str
    prompt_primary: str
    prompt_secondary: str = ""
    prompt_audio_url: Optional[str] = None
    accepted_answers: list[str] = dataclasses.field(default_factory=list)
    choices: list[str] = dataclasses.field(default_factory=list)
    verb_fields: list[VerbField] = dataclasses.field(default_factory=list)
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class CardStats(DictLikeState):
    attempts: int = 0
    correct: int = 0
    incorrect: int = 0


@dataclasses.dataclass
class StatsState(DictLikeState):
    card_stats: dict[str, CardStats] = dataclasses.field(default_factory=dict)
    wrong_card_ids: set[str] = dataclasses.field(default_factory=set)


@dataclasses.dataclass
class RunConfig(DictLikeState):
    quiz_mode: str = GENERAL_MODE
    failed_only: bool = False
    max_cards: int = 20
    mcq_ratio: int = 50
    text_ratio: int = 50
    full_ratio: int = 50


@dataclasses.dataclass
class RunSummary(DictLikeState):
    total_cards: int = 0
    answered: int = 0
    correct: int = 0
    incorrect: int = 0
    completed: bool = False


@dataclasses.dataclass
class FeedbackState(DictLikeState):
    correct: bool
    answers: dict[str, str]
    expected: dict[str, str]


@dataclasses.dataclass
class SessionState(DictLikeState):
    stage: str = "config"
    run_config: RunConfig = dataclasses.field(default_factory=RunConfig)
    queue: list[StudyCard] = dataclasses.field(default_factory=list)
    index: int = 0
    feedback: Optional[FeedbackState] = None
    text_answer: str = ""
    text_hint_count: int = 0
    verb_answers: dict[str, str] = dataclasses.field(default_factory=dict)
    verb_hint_counts: dict[str, int] = dataclasses.field(default_factory=dict)
    summary: RunSummary = dataclasses.field(default_factory=RunSummary)


@dataclasses.dataclass
class LibraryState(DictLikeState):
    general_entries: list[GeneralEntry] = dataclasses.field(default_factory=list)
    verb_entries: list[VerbEntry] = dataclasses.field(default_factory=list)
    number_entries: list[NumberEntry] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class UIState(DictLikeState):
    active_tab: str = "quiz"
    selected_quiz_mode: str = GENERAL_MODE
    loading: bool = True
    error: Optional[str] = None
    ready: bool = False


@dataclasses.dataclass
class AppState(DictLikeState):
    library: LibraryState = dataclasses.field(default_factory=LibraryState)
    stats: StatsState = dataclasses.field(default_factory=StatsState)
    session: SessionState = dataclasses.field(default_factory=SessionState)


def default_app_state() -> AppState:
    return AppState()


def default_ui_state() -> UIState:
    return UIState()


app_state = default_app_state()
ui_state = default_ui_state()
