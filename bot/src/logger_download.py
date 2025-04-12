import logging
import logging.config
import os

import yaml

LOGGING_CFG_PATH = "src/configs/logging.cfg.yml"


def get_logger(logging_cfg_path: str = None) -> logging.Logger:
    """
    Create logger object with params from config.
    -------
    Returns
    logging.Logger
    """
    with open(logging_cfg_path) as stream:
        config = yaml.safe_load(stream.read())
        logger_name = list(config.get("loggers").keys())[0]
        logger_model = logging.getLogger(logger_name)
        logging.config.dictConfig(config)

    return logger_model


logger = get_logger(logging_cfg_path=LOGGING_CFG_PATH)
