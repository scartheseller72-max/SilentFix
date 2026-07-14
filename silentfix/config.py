from silentfix.core.types import Config

_default_config = Config()

def get_config() -> Config:
    return _default_config

def set_config(**kwargs):
    for k, v in kwargs.items():
        if hasattr(_default_config, k):
            setattr(_default_config, k, v)
