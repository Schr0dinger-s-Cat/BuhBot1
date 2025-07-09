import logging

logger = init_logger(
    name="my_app",
    log_level=logging.DEBUG,
    log_to_console=True,
    log_to_file=True,
    log_file="logs/app.log"
)