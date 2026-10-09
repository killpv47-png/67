from aiogram.fsm.state import State, StatesGroup


class Onboard(StatesGroup):
    lang = State()
    token = State()


class NewRepo(StatesGroup):
    name = State()
    owner = State()
    desc = State()
    vis = State()
    readme = State()
    gitignore = State()
    license = State()
    features = State()


class Upload(StatesGroup):
    repo = State()
    zip = State()
    wipe = State()
    root = State()
    branch = State()
    message = State()


class SecretFlow(StatesGroup):
    name = State()
    value = State()
    var_name = State()
    var_value = State()


class RepoEdit(StatesGroup):
    desc = State()
    branch = State()
    delete_confirm = State()


class ActionsFlow(StatesGroup):
    ref = State()


class AISetup(StatesGroup):
    base = State()
    key = State()
    model = State()
